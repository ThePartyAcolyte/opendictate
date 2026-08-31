#!/usr/bin/env python3
"""
OpenDictate Daemon Entry Point.

Modularized master service orchestrating Speech-to-Text inference (Faster-Whisper),
audio capture, Gemini LLM text post-processing, IPC Unix Socket server, GTK OSD bubble,
and System Tray integration.
"""

import os
os.environ["GDK_BACKEND"] = "x11"

import sys
import re
import json
import time
import socket
import shutil
import logging
import threading
import subprocess
import signal
import numpy as np
from typing import Dict, Any, Optional, Tuple
from logging.handlers import RotatingFileHandler

# Initialize logging
LOG_DIR = os.path.expanduser("~/.local/share/opendictate")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "daemon.log")
logging.basicConfig(
    handlers=[RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=1)],
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True
)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from i18n import get_translator
from core.config import ConfigManager, CONFIG_PATH, is_api_available
from core.audio import AudioRecorder
from core.engine import WhisperEngine
from core.gemini_live_engine import GeminiLiveEngine
from core.vad import VADStreamSegmenter
from core.llm import LLMService
from core.mpris import MediaController
from core.aec import EchoCancelManager
from core.voice_commands import VoiceCommandManager
from core.audio_concurrency import is_microphone_in_use_by_other_apps
from core.ipc import IPCServer, SOCKET_PATH
from core.window_utils import get_active_window_info, restore_window_focus
from ui.bubble import BubbleWindow
from ui.tray import TrayManager


class DictationDaemon:
    """Master orchestrator for OpenDictate services and UI state machine."""

    def __init__(self) -> None:
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config()
        self.i18n = get_translator(self.config.get("ui_language", "en"))

        self.audio = AudioRecorder()
        self.engine = WhisperEngine()
        self.gemini_live_engine = GeminiLiveEngine()
        self.vad_segmenter = VADStreamSegmenter(config=self.config)
        self.llm = LLMService(self.config_manager)
        self.media = MediaController()
        self.aec = EchoCancelManager()
        self.saturation_detector = self.aec.saturation_detector
        self.saturation_detector.on_state_change = self._on_saturation_state_changed
        self.voice_commands = VoiceCommandManager(self.config, on_command_detected=self._on_voice_command_detected)
        self._idle_voice_proc: Optional[subprocess.Popen] = None
        self._idle_voice_running: bool = False
        self._idle_voice_lock = threading.Lock()
        self.voice_listener_paused_by_ui: bool = False

        self.state: str = "IDLE"
        self.next_action: Optional[str] = None
        self.last_original_text: str = ""
        self.current_text: str = ""
        self.confirmed_text: str = ""
        self.last_transcribed_time: float = 0.0
        self.transcribe_lock = threading.Lock()

        self.start_time: float = 0.0
        self.pause_start_time: float = 0.0
        self.total_paused_time: float = 0.0
        self.processing_start_time: float = 0.0
        self._last_state_export_time: float = 0.0
        self.timer_id: Optional[int] = None
        self.config_window = None
        self.wizard_window = None
        self.update_window = None

        self.current_app_class: str = "unknown"
        self.current_window_title: str = "unknown"

        # UI Components
        self.bubble = BubbleWindow(
            config=self.config,
            i18n=self.i18n,
            on_toggle_record_pause=self.action_record,
            on_send=self.action_send,
            on_cancel=self.action_cancel
        )
        self.tray = TrayManager(
            config=self.config,
            i18n=self.i18n,
            on_toggle_record_pause=self.on_tray_record_clicked,
            on_toggle_auto_send=self.on_auto_send_toggled,
            on_toggle_ai=self.on_ai_toggled,
            on_open_config=self.open_config_window,
            on_quit=self.quit_app,
            show_notification=self.show_notification
        )
        self.resolve_bubble_mode()

        # Start IPC socket server thread
        self.ipc_handlers = {
            "record": lambda: GLib.idle_add(self.action_record),
            "pause": lambda: GLib.idle_add(self.action_pause),
            "cancel": lambda: GLib.idle_add(self.action_cancel),
            "send": lambda: GLib.idle_add(self.action_send),
            "cycle-model": lambda: GLib.idle_add(self.action_cycle_model),
            "toggle-ai": lambda: GLib.idle_add(self.action_toggle_ai),
            "toggle-autosend": lambda: GLib.idle_add(self.action_toggle_autosend),
            "toggle-realtime": lambda: GLib.idle_add(self.action_toggle_realtime),
            "toggle-bubble": lambda: GLib.idle_add(self.action_toggle_bubble),
            "toggle-record-send": lambda: GLib.idle_add(self.action_record),
            "finish-normal": lambda: GLib.idle_add(self.action_finish_normal),
            "finish-ai": lambda: GLib.idle_add(self.action_finish_ai),
            "quit": lambda: GLib.idle_add(self.quit_app),
            "settings": lambda: GLib.idle_add(self.open_config_window),
            "wizard": lambda: GLib.idle_add(self.open_wizard_window),
            "check-updates": lambda: GLib.idle_add(self.action_check_updates),
            "update-dialog": lambda: GLib.idle_add(self.open_update_window),
            "reload-config": lambda: GLib.idle_add(self.on_config_saved),
            "pause-voice-listener": lambda: GLib.idle_add(self._pause_voice_listener_by_ui),
            "resume-voice-listener": lambda: GLib.idle_add(self._resume_voice_listener_by_ui),
        }
        self.ipc = IPCServer(self.ipc_handlers)
        threading.Thread(target=self.ipc.start, daemon=True).start()

        # Check first run onboarding
        if not self.config.get("initial_setup_completed", False):
            GLib.idle_add(self.open_wizard_window)
        else:
            self._start_idle_voice_command_listener()

        # Initial model load
        backend = self.config.get("stt_backend", "local_whisper")
        if backend == "gemini_live" and self.config.get("api_key"):
            logging.info("STT backend is Gemini Live. Skipping local Faster-Whisper model load to save RAM.")
            self.state = "IDLE"
            self.export_state()
        else:
            model_size = self.config.get("whisper_model_size", "medium")
            self.load_model_async(model_size)

        # Check for updates in background
        from core.updater import check_for_updates
        check_for_updates(self.config, self.config_manager, on_update_found=self.open_update_window)

    # -------------------------------------------------------------------------
    # Notification & Sound Helpers
    # -------------------------------------------------------------------------
    def show_notification(self, title: str, message: str, timeout: int = 1500) -> None:
        """Dispatch desktop notification using libnotify/notify-send.

        Args:
            title: Notification title string.
            message: Notification body text string.
            timeout: Display duration in milliseconds (default 1500).
        """
        if not self.config.get("show_notifications", True):
            return
        try:
            subprocess.Popen([
                "notify-send",
                "-h", "string:x-canonical-private-synchronous:dictate",
                "-t", str(timeout),
                title, message
            ])
        except Exception as e:
            logging.error(f"Error dispatching system notification: {e}")

    def play_sound(self, sound_path: str) -> None:
        """Play feedback audio cue using PipeWire pw-play.

        Args:
            sound_path: Absolute file path to audio cue asset.
        """
        if os.path.exists(sound_path):
            subprocess.Popen(["pw-play", sound_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def export_state(self, force: bool = True) -> None:
        """Export state telemetry to /tmp/opendictate_state.json for GNOME extension / OpenDeck.

        Args:
            force: If True, bypasses throttling interval check (0.1s).
        """
        now = time.time()
        if not force and (now - self._last_state_export_time < 0.1):
            return
        self._last_state_export_time = now

        status_key_map = {
            "RECORDING": "recording",
            "PAUSED": "paused",
            "TRANSCRIBING": "transcribing",
            "CLEANING": "cleaning",
            "PROCESSING": "processing",
            "LOADING": "loading_model",
            "IDLE": "ready",
            "OFFLINE": "offline_no_models"
        }
        key = status_key_map.get(self.state, "processing")
        backend = self.config.get("stt_backend", "local_whisper")
        if key == "ready":
            if backend == "gemini_live" and self.config.get("api_key"):
                status_text = "Listo (Gemini Live)"
            else:
                status_text = self.i18n.t("ready", self.engine.model_size)
        elif key == "recording" and backend == "gemini_live":
            status_text = "Grabando (Gemini Live)..."
        else:
            status_text = self.i18n.t(key)

        state_data = {
            "state": self.state,
            "status_text": status_text,
            "stt_backend": backend,
            "ui_language": self.config.get("ui_language", "en"),
            "time_str": getattr(self, "last_time_str", "00:00"),
            "model": self.engine.model_size,
            "level": getattr(self.audio, "audio_level", 0.0),
            "ai_enabled": self.config.get("ai_enabled", False),
            "autosend_enabled": self.config.get("auto_send", False),
            "autopause_enabled": self.config.get("auto_pause_media", True),
            "voice_commands_enabled": self.config.get("voice_commands_enabled", False),
            "mic_health": self.saturation_detector.current_state,
            "realtime_enabled": self.config.get("realtime_mode", True),
            "hide_bubble": self.config.get("hide_bubble", False),
            "restore_window_focus": self.config.get("restore_window_focus", False),
            "send_status": getattr(self, "send_status", "idle"),
            "start_time": self.start_time,
            "pause_start_time": self.pause_start_time,
            "total_paused_time": self.total_paused_time
        }
        try:
            tmp_path = f"/tmp/opendictate_state_{os.getpid()}.json.tmp"
            with open(tmp_path, "w") as f:
                json.dump(state_data, f)
            os.replace(tmp_path, "/tmp/opendictate_state.json")
        except Exception as e:
            logging.debug(f"Error exporting state JSON: {e}")

    def quit_app(self) -> None:
        """Export OFFLINE state telemetry and exit GTK main loop."""
        try:
            state_data = {
                "state": "OFFLINE",
                "status_text": "Offline",
                "ui_language": self.config.get("ui_language", "en")
            }
            tmp_path = f"/tmp/opendictate_state_{os.getpid()}.json.tmp"
            with open(tmp_path, "w") as f:
                json.dump(state_data, f)
            os.replace(tmp_path, "/tmp/opendictate_state.json")
        except Exception as e:
            logging.debug(f"Error exporting OFFLINE state: {e}")
        Gtk.main_quit()

    # -------------------------------------------------------------------------
    # Model Loading
    # -------------------------------------------------------------------------
    def load_model_async(self, size: str) -> None:
        """Asynchronously load specified Whisper model size with multi-tier fallback.

        Args:
            size: Model size identifier string (e.g. 'tiny', 'base', 'small', 'medium').
        """
        self.state = "LOADING"
        self.update_status(self.i18n.t("loading_model_param", size=size))
        self.export_state()

        def _loader():
            success, loaded_size, status_code = self.engine.load_model(size, self.config)
            if success and loaded_size:
                self.config["whisper_model_size"] = loaded_size
                self.config_manager.save_config(self.config)
                if status_code == "fallback_local":
                    GLib.idle_add(
                        self.show_notification,
                        "OpenDictate",
                        self.i18n.t("fallback_model_loaded", requested=size, loaded=loaded_size),
                        4000
                    )
                GLib.idle_add(self.reset_state)
            else:
                GLib.idle_add(self.handle_initialization_failure)

        threading.Thread(target=_loader, daemon=True).start()

    def handle_initialization_failure(self) -> None:
        """Handle total failure when no models are cached and no internet connection exists."""
        self.state = "OFFLINE"
        status_text = self.i18n.t("offline_no_models")
        self.update_status(status_text)
        self.export_state()
        self.show_notification(
            self.i18n.t("error_whisper"),
            self.i18n.t("error_no_models_offline"),
            5000
        )

    def resolve_bubble_mode(self) -> None:
        """Resolve whether the floating bubble should be in interactive or minimalist text mode."""
        mode = self.config.get("bubble_mode", "auto")
        if mode == "interactive":
            self.bubble.set_interactive_mode(True)
        elif mode == "text":
            self.bubble.set_interactive_mode(False)
        else:  # "auto"
            is_gnome_ext = False
            try:
                res = subprocess.run(
                    ["gnome-extensions", "show", "com.kirulab.opendictate@kirulab.com"],
                    capture_output=True, text=True, timeout=0.8
                )
                if res.returncode == 0 and ("State: ENABLED" in res.stdout or "State: 1" in res.stdout or "ENABLED" in res.stdout):
                    is_gnome_ext = True
            except Exception:
                pass
            self.bubble.set_interactive_mode(not is_gnome_ext)

    # -------------------------------------------------------------------------
    # Voice Commands & Saturation Monitoring
    # -------------------------------------------------------------------------
    def _on_saturation_state_changed(self, new_state: str) -> None:
        """Callback when microphone saturation changes (HEALTHY vs CLIPPED)."""
        GLib.idle_add(self.tray.set_mic_health, new_state)
        self.export_state(force=True)

    def _on_voice_command_detected(self, action: str, confidence: float, duration_sec: float = 0.8) -> None:
        """Handle recognized voice commands and trim command utterance audio from the stream."""
        logging.info(f"Triggering action for voice command: {action} (confidence: {confidence:.2f}, duration: {duration_sec:.2f}s)")
        self.voice_commands.reset_buffer(cooldown=2.0)

        # Trim command utterance from audio buffer so it does not get transcribed by Whisper
        if action in ("SEND", "CANCEL", "PAUSE") and self.state in ("RECORDING", "PAUSED"):
            trim_bytes = int((duration_sec + 0.20) * 16000 * 2)
            if len(self.audio.audio_buffer) > trim_bytes:
                del self.audio.audio_buffer[-trim_bytes:]
                logging.info(f"Trimmed {trim_bytes} trailing PCM bytes ({duration_sec + 0.20:.2f}s) of '{action}' command from audio buffer.")

        if action == "START" and self.state == "IDLE":
            GLib.idle_add(self.action_record)
        elif action == "SEND" and self.state in ("RECORDING", "PAUSED"):
            GLib.idle_add(self.action_send)
        elif action == "PAUSE" and self.state in ("RECORDING", "PAUSED"):
            GLib.idle_add(self.action_pause)
        elif action == "CANCEL" and self.state in ("RECORDING", "PAUSED"):
            GLib.idle_add(self.action_cancel)

    def _pause_voice_listener_by_ui(self) -> None:
        """Explicitly pause idle listening when a modal configuration or sample recording UI is open."""
        self.voice_listener_paused_by_ui = True
        self._stop_idle_voice_command_listener()

    def _resume_voice_listener_by_ui(self) -> None:
        """Resume idle listening when modal UI closes."""
        self.voice_listener_paused_by_ui = False
        if self.config.get("voice_commands_enabled", False) and self.state == "IDLE":
            self._start_idle_voice_command_listener()

    def _start_idle_voice_command_listener(self) -> None:
        """Start background microphone listener for START wake word when in IDLE."""
        if not self.config.get("voice_commands_enabled", False) or self.state != "IDLE" or self.voice_listener_paused_by_ui:
            return

        with self._idle_voice_lock:
            self._stop_idle_voice_command_listener_locked()
            self.voice_commands.reset_buffer(cooldown=1.2)
            self._idle_voice_running = True
            threading.Thread(target=self._idle_voice_worker, daemon=True).start()

    def _stop_idle_voice_command_listener(self) -> None:
        """Stop idle background microphone listener safely."""
        with self._idle_voice_lock:
            self._stop_idle_voice_command_listener_locked()

    def _stop_idle_voice_command_listener_locked(self) -> None:
        """Internal lock-guarded process termination."""
        self._idle_voice_running = False
        if self._idle_voice_proc:
            proc = self._idle_voice_proc
            self._idle_voice_proc = None
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=0.3)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass

    def _idle_voice_worker(self) -> None:
        """Worker loop reading low-overhead PCM chunks for wake word during IDLE with auto mic-release."""
        dev = self.aec.get_preferred_capture_device()
        cmd = ["arecord", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", "16000"]
        if dev and dev != "default":
            cmd.extend(["-D", dev])

        last_concurrency_check = 0.0
        active_proc = None

        try:
            with self._idle_voice_lock:
                if not self._idle_voice_running or self.state != "IDLE" or self.voice_listener_paused_by_ui:
                    return
                self._idle_voice_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                active_proc = self._idle_voice_proc

            while self._idle_voice_running and self.state == "IDLE" and not self.voice_listener_paused_by_ui and active_proc and active_proc.stdout:
                # Periodic mic concurrency check every 2.0s
                now = time.time()
                if now - last_concurrency_check > 2.0:
                    last_concurrency_check = now
                    is_in_use, ext_app = is_microphone_in_use_by_other_apps(os.getpid())
                    if is_in_use:
                        logging.info(f"Microphone requested by external app '{ext_app}'. Suspending idle listener.")
                        with self._idle_voice_lock:
                            if self._idle_voice_proc == active_proc:
                                self._stop_idle_voice_command_listener_locked()
                        # Sleep loop until external app finishes
                        while self._idle_voice_running and self.state == "IDLE" and not self.voice_listener_paused_by_ui:
                            time.sleep(1.5)
                            still_in_use, _ = is_microphone_in_use_by_other_apps(os.getpid())
                            if not still_in_use:
                                logging.info("External application released microphone. Resuming idle listener.")
                                break
                        if self._idle_voice_running and self.state == "IDLE" and not self.voice_listener_paused_by_ui:
                            self._start_idle_voice_command_listener()
                        return

                chunk = active_proc.stdout.read(1024)
                if not chunk:
                    break
                self.saturation_detector.process_pcm_chunk(chunk)
                self.voice_commands.process_pcm_stream(
                    chunk,
                    current_daemon_state="IDLE",
                    is_saturated=self.saturation_detector.is_clipped
                )
        except Exception as e:
            logging.debug(f"Idle voice worker ended: {e}")
        finally:
            with self._idle_voice_lock:
                if self._idle_voice_proc == active_proc:
                    self._stop_idle_voice_command_listener_locked()

    def _on_live_interim_text(self, interim: str) -> None:
        """Render speculative live partial transcription in OSD bubble."""
        if self.state in ["RECORDING", "TRANSCRIBING"]:
            display = f"{self.confirmed_text} {interim}".strip() if self.confirmed_text else interim
            self.bubble.set_live_text(display)

    def _on_live_final_text(self, final_text: str) -> None:
        """Update confirmed transcript from Gemini Live STT."""
        if self.state in ["RECORDING", "TRANSCRIBING"]:
            self.confirmed_text = final_text
            self.bubble.set_live_text(self.confirmed_text)

    def _on_live_stt_error(self, err: Exception) -> None:
        """Handle Live STT connection error."""
        logging.error(f"Gemini Live STT error: {err}")

    # -------------------------------------------------------------------------
    # Recording Lifecycle
    # -------------------------------------------------------------------------
    def start_recording(self) -> None:
        """Initiate audio capture lifecycle and spawn processing threads."""
        use_gemini_live = (self.config.get("stt_backend", "local_whisper") == "gemini_live" and is_api_available(self.config))
        if not use_gemini_live and not self.engine.model:
            self.show_notification("OpenDictate", self.i18n.t("error_no_models_offline"))
            return

        self._stop_idle_voice_command_listener()
        self.voice_commands.reset_buffer(cooldown=1.5)
        self.current_app_class, self.current_window_title = get_active_window_info()
        self.play_sound("/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga")
        self.media.pause_media(self.config)

        self.state = "RECORDING"
        self.start_time = time.time()
        self.total_paused_time = 0
        self.pause_start_time = 0
        self.confirmed_text = ""
        self.last_transcribed_time = 0.0
        self.vad_segmenter.reset()
        self.vad_segmenter.update_config(self.config)

        self.resolve_bubble_mode()
        if not self.config.get("hide_bubble", False):
            self.bubble.show_recording_state(start_time=self.start_time, total_paused_time=self.total_paused_time)

        self.tray.set_daemon_state("RECORDING")

        if self.timer_id:
            GLib.source_remove(self.timer_id)
        self.timer_id = GLib.timeout_add(100, self.update_timer)

        self.audio.start_recording(device=self.aec.get_preferred_capture_device())
        threading.Thread(target=self._audio_stream_loop, daemon=True).start()

        if use_gemini_live:
            api_key = self.config.get("api_key", "").strip()
            self.gemini_live_engine.start_session(
                api_key=api_key,
                config=self.config,
                on_interim_text=lambda interim: GLib.idle_add(self._on_live_interim_text, interim),
                on_final_text=lambda final_text: GLib.idle_add(self._on_live_final_text, final_text),
                on_error=lambda err: GLib.idle_add(self._on_live_stt_error, err)
            )
        elif self.config.get("realtime_mode", True):
            self.streaming_thread = threading.Thread(target=self._streaming_transcriber_loop, daemon=True)
            self.streaming_thread.start()

    def _audio_stream_loop(self) -> None:
        """Lightweight non-blocking audio streaming worker thread reading PCM buffers from arecord stdout."""
        while self.state in ["RECORDING", "PAUSED"]:
            last_buf_len = len(self.audio.audio_buffer)
            success = self.audio.process_stream_chunk(
                chunk_size=1024,
                is_paused=(self.state == "PAUSED"),
                on_level_update=lambda lvl: (self.export_state(force=False), GLib.idle_add(self.bubble.update_audio_level, lvl))
            )
            if not success:
                break

            new_buf_len = len(self.audio.audio_buffer)
            if new_buf_len > last_buf_len:
                new_chunk = bytes(self.audio.audio_buffer[last_buf_len:new_buf_len])
                self.saturation_detector.process_pcm_chunk(new_chunk)
                if self.gemini_live_engine.is_active():
                    self.gemini_live_engine.send_audio_chunk(new_chunk)


    def _streaming_transcriber_loop(self) -> None:
        """Adaptive VAD-based transcription and silence-gated tail voice command worker loop."""
        bytes_per_sec = 16000 * 2
        last_vad_byte_offset = 0
        last_checked_speech_end = -1.0

    def _transcribe_and_accumulate_chunk(self, chunk_start: float, chunk_end: float, bytes_per_sec: int = 32000) -> None:
        """Helper to slice and transcribe a speech chunk with Faster-Whisper."""
        start_idx = int(chunk_start * bytes_per_sec)
        end_idx = int(chunk_end * bytes_per_sec)
        chunk_bytes = bytes(self.audio.audio_buffer[start_idx:end_idx])
        if len(chunk_bytes) % 2 != 0:
            chunk_bytes = chunk_bytes[:-1]

        if len(chunk_bytes) >= 9600:  # Minimum 0.3s audio slice
            try:
                audio_int16 = np.frombuffer(chunk_bytes, dtype=np.int16)
                audio_float32 = audio_int16.astype(np.float32) / 32768.0

                with self.transcribe_lock:
                    prompt = self.confirmed_text[-200:] if self.confirmed_text else None
                    t_start = time.perf_counter()
                    segments, _ = self.engine.transcribe_chunk(audio_float32, self.config, initial_prompt=prompt)
                    t_transcribe = time.perf_counter() - t_start

                    chunk_text = "".join(seg.text for seg in segments).strip()

                    if chunk_text and self.state in ["RECORDING", "TRANSCRIBING"]:
                        if self.confirmed_text and not self.confirmed_text.endswith(" ") and not chunk_text.startswith(" "):
                            self.confirmed_text += " "
                        self.confirmed_text += chunk_text
                        GLib.idle_add(self.bubble.set_live_text, self.confirmed_text)

                    logging.info(
                        f"VAD chunk transcribed in {t_transcribe:.2f}s | "
                        f"Audio: [{chunk_start:.2f}s -> {chunk_end:.2f}s] ({chunk_end - chunk_start:.2f}s) | "
                        f"Text: '{chunk_text}'"
                    )
            except Exception as e:
                logging.error(f"Streaming transcription error: {e}", exc_info=True)

    def _streaming_transcriber_loop(self) -> None:
        """Adaptive VAD-based streaming transcription with non-blocking keyword holding queue."""
        bytes_per_sec = 16000 * 2
        last_vad_byte_offset = 0
        
        # Structure of pending_chunk: (chunk_start_sec, chunk_cut_sec, cut_audio_time_sec)
        pending_chunk: Optional[Tuple[float, float, float]] = None

        while self.state in ["RECORDING", "PAUSED"]:
            if self.state == "PAUSED":
                time.sleep(0.1)
                continue

            current_buffer_len = len(self.audio.audio_buffer)

            # Ingest newly captured PCM bytes into VAD segmenter
            if current_buffer_len > last_vad_byte_offset:
                new_pcm = bytes(self.audio.audio_buffer[last_vad_byte_offset:current_buffer_len])
                self.vad_segmenter.process_pcm_chunk(new_pcm)
                last_vad_byte_offset = current_buffer_len

            current_time = current_buffer_len / bytes_per_sec
            voice_enabled = self.config.get("voice_commands_enabled", False)
            silence_pause_timeout = float(self.config.get("voice_command_silence_pause", 1.5))

            # -----------------------------------------------------------------
            # 1. Evaluate Holding Queue if a chunk is pending
            # -----------------------------------------------------------------
            if pending_chunk is not None:
                chunk_start, chunk_end, cut_time = pending_chunk
                silence_elapsed = current_time - cut_time
                speech_resumed = (self.vad_segmenter.last_speech_time > chunk_end)

                if speech_resumed or (not voice_enabled):
                    # User resumed speaking before silence timeout (normal speech cadence) -> dispatch chunk
                    self._transcribe_and_accumulate_chunk(chunk_start, chunk_end, bytes_per_sec)
                    self.last_transcribed_time = chunk_end
                    pending_chunk = None

                elif silence_elapsed >= silence_pause_timeout:
                    # Silence exceeded configured timeout -> evaluate keyword on chunk's trailing speech
                    speech_start = max(chunk_start, chunk_end - 1.5)
                    start_b = int(speech_start * bytes_per_sec)
                    end_b = int(chunk_end * bytes_per_sec)
                    tail_bytes = bytes(self.audio.audio_buffer[start_b:end_b])

                    cmd_res = None
                    if len(tail_bytes) >= 6400:
                        tail_float32 = np.frombuffer(tail_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                        cmd_res = self.voice_commands.evaluate_audio_segment(tail_float32, current_daemon_state=self.state)

                    if cmd_res:
                        action, conf, duration = cmd_res
                        logging.info(
                            f"Holding-stage voice command triggered: {action} "
                            f"(confidence: {conf:.2f}, silence: {silence_elapsed:.2f}s, cmd_duration: {duration:.2f}s)"
                        )
                        vad_pad = float(self.config.get("vad_speech_pad_ms", 400)) / 1000.0
                        clean_end = max(chunk_start, chunk_end - vad_pad - duration - 0.10)

                        # Completely trim trailing audio (command + pause + dtw latency) from master buffer
                        trim_byte_offset = int(clean_end * bytes_per_sec)
                        if len(self.audio.audio_buffer) > trim_byte_offset:
                            del self.audio.audio_buffer[trim_byte_offset:]

                        # Transcribe clean speech portion before the command if non-empty
                        if clean_end - chunk_start > 0.3:
                            self._transcribe_and_accumulate_chunk(chunk_start, clean_end, bytes_per_sec)

                        self.last_transcribed_time = clean_end
                        pending_chunk = None

                        if action == "SEND":
                            GLib.idle_add(self.action_send)
                            break
                        elif action == "PAUSE":
                            GLib.idle_add(self.action_pause)
                        elif action == "CANCEL":
                            GLib.idle_add(self.action_cancel)
                            break
                    else:
                        # No command detected on pause -> dispatch chunk to Whisper
                        self._transcribe_and_accumulate_chunk(chunk_start, chunk_end, bytes_per_sec)
                        self.last_transcribed_time = chunk_end
                        pending_chunk = None

            # -----------------------------------------------------------------
            # 2. Check for new VAD cut point
            # -----------------------------------------------------------------
            if pending_chunk is None:
                cut_point = self.vad_segmenter.find_cut_point(current_time, self.last_transcribed_time)
                if cut_point is not None and cut_point > self.last_transcribed_time:
                    chunk_start = self.last_transcribed_time
                    chunk_end = cut_point
                    self.vad_segmenter.advance_cut(chunk_end)

                    if voice_enabled:
                        # Hold the chunk in non-blocking queue to await silence timeout or resumed speech
                        pending_chunk = (chunk_start, chunk_end, current_time)
                    else:
                        # Voice commands disabled: direct dispatch
                        self._transcribe_and_accumulate_chunk(chunk_start, chunk_end, bytes_per_sec)
                        self.last_transcribed_time = chunk_end

            time.sleep(0.1)

    def stop_recording(self) -> None:
        """Stop audio capture, resume external media playback, and trigger final STT decoding."""
        self.state = "TRANSCRIBING"
        self.processing_start_time = time.time()
        self.update_status(self.i18n.t("transcribing"))

        self.audio.stop_recording()
        self.media.resume_media()
        self.play_sound("/usr/share/sounds/freedesktop/stereo/device-removed.oga")

        if not self.config.get("hide_bubble", False):
            self.bubble.show_processing_state(self.i18n.t("transcribing"))
        self.tray.set_daemon_state("TRANSCRIBING")

        threading.Thread(target=self._final_transcribe_loop, daemon=True).start()

    def _final_transcribe_loop(self) -> None:
        """Execute final transcription pass (full-batch or remaining audio tail)."""
        if hasattr(self, 'streaming_thread') and self.streaming_thread and self.streaming_thread.is_alive():
            logging.info("Waiting for streaming loop to finish current chunk...")
            self.streaming_thread.join()

        try:
            bytes_per_sec = 16000 * 2
            current_audio_time = len(self.audio.audio_buffer) / bytes_per_sec

            with self.transcribe_lock:
                if self.config.get("stt_backend", "local_whisper") == "gemini_live" and self.gemini_live_engine.is_active():
                    live_text = self.gemini_live_engine.stop_session(timeout=2.0)
                    if live_text:
                        self.confirmed_text = live_text
                elif not self.config.get("realtime_mode", True):
                    logging.info("Executing full audio batch transcription...")
                    chunk_bytes = bytes(self.audio.audio_buffer)
                    if len(chunk_bytes) % 2 != 0:
                        chunk_bytes = chunk_bytes[:-1]

                    if chunk_bytes:
                        if self.engine.model is None:
                            logging.info("On-demand load of Faster-Whisper for full audio batch...")
                            self.engine.load_model(self.config.get("whisper_model_size", "medium"), self.config)

                        audio_int16 = np.frombuffer(chunk_bytes, dtype=np.int16)
                        audio_float32 = audio_int16.astype(np.float32) / 32768.0

                        segments, _ = self.engine.transcribe_chunk(audio_float32, self.config)
                        full_text = "".join(seg.text for seg in segments).strip()
                        self.confirmed_text = full_text
                else:
                    remaining_duration = current_audio_time - self.last_transcribed_time
                    if remaining_duration > 0.35:
                        start_idx = int(self.last_transcribed_time * bytes_per_sec)
                        chunk_bytes = bytes(self.audio.audio_buffer[start_idx:])
                        if len(chunk_bytes) % 2 != 0:
                            chunk_bytes = chunk_bytes[:-1]

                        if chunk_bytes:
                            if self.engine.model is None:
                                logging.info("On-demand load of Faster-Whisper for remaining tail...")
                                self.engine.load_model(self.config.get("whisper_model_size", "medium"), self.config)

                            audio_int16 = np.frombuffer(chunk_bytes, dtype=np.int16)
                            audio_float32 = audio_int16.astype(np.float32) / 32768.0

                            prompt = self.confirmed_text[-200:] if self.confirmed_text else None
                            t_start = time.perf_counter()
                            segments, _ = self.engine.transcribe_chunk(audio_float32, self.config, initial_prompt=prompt)
                            t_transcribe = time.perf_counter() - t_start

                            chunk_text = "".join(seg.text for seg in segments).strip()
                            if chunk_text:
                                if self.confirmed_text and not self.confirmed_text.endswith(" ") and not chunk_text.startswith(" "):
                                    self.confirmed_text += " "
                                self.confirmed_text += chunk_text

                            logging.info(
                                f"Final audio tail transcribed in {t_transcribe:.2f}s | "
                                f"Audio: [{self.last_transcribed_time:.2f}s -> {current_audio_time:.2f}s] ({remaining_duration:.2f}s) | "
                                f"Text: '{chunk_text}'"
                            )
                            self.last_transcribed_time = current_audio_time

            final_text = self.confirmed_text.strip()
            logging.info(f"Final transcript text: '{final_text}'")
            GLib.idle_add(self._process_transcribed_text, final_text)

        except Exception as e:
            logging.error(f"Error during final transcription: {e}", exc_info=True)
            GLib.idle_add(self.reset_state)

    def _strip_trailing_command_phrases(self, text: str) -> str:
        """Sanitize transcription tail by removing matching command trigger phrases."""
        if not text or not hasattr(self, "voice_commands"):
            return text

        try:
            phrases_to_strip = []
            for action in ("SEND", "PAUSE", "CANCEL"):
                for phrase in self.voice_commands.phrases_by_action.get(action, []):
                    name = phrase.name.strip()
                    if name:
                        phrases_to_strip.append(re.escape(name))
                        clean_name = re.sub(r'[,.!?]', '', name).strip()
                        if clean_name and clean_name != name:
                            phrases_to_strip.append(re.escape(clean_name))

            if not phrases_to_strip:
                return text

            pattern = re.compile(
                r'[\s,.;:!?]+(?:' + '|'.join(phrases_to_strip) + r')[\s,.;:!?]*$',
                re.IGNORECASE
            )
            return pattern.sub('', text).strip()
        except Exception as e:
            logging.error(f"Error in _strip_trailing_command_phrases: {e}", exc_info=True)
            return text

    def _process_transcribed_text(self, text: str) -> None:
        """Route finalized transcript through AI cleanup if enabled or directly to paste.

        Args:
            text: Transcribed text string.
        """
        try:
            if self.state == "IDLE":
                logging.info("Transcribed text received while IDLE (canceled). Aborting.")
                return

            text = self._strip_trailing_command_phrases(text)

            if not text:
                logging.info("Transcription yielded empty text after command stripping. Resetting state.")
                self.reset_state()
                return

            self.last_original_text = text

            app_prompt, enable_vision = self.config_manager.get_app_profile(self.current_app_class)
            has_app_override = bool(app_prompt or enable_vision)

            use_llm = False
            if self.next_action == "FINISH_AI":
                use_llm = True
            elif self.next_action == "FINISH_NORMAL":
                use_llm = False
            else:
                use_llm = self.config.get("ai_enabled", False) or has_app_override

            # Bypass separate LLM pass if using Gemini Live SMART mode without AI toggle or overrides
            is_gemini_live = (self.config.get("stt_backend", "local_whisper") == "gemini_live")
            is_smart_mode = (self.config.get("gemini_live_mode", "SMART") == "SMART")
            if is_gemini_live and is_smart_mode and not use_llm:
                self.finalize_text(text)
                return

            if use_llm and is_api_available(self.config):
                self.state = "CLEANING"
                self.processing_start_time = time.time()
                if not self.config.get("hide_bubble", False):
                    self.bubble.show_processing_state(self.i18n.t("cleaning"))
                self.tray.set_daemon_state("CLEANING")
                self.update_status(self.i18n.t("cleaning"))
                threading.Thread(target=self._llm_clean_loop, args=(text,), daemon=True).start()
            else:
                self.finalize_text(text)
        except Exception as e:
            logging.error(f"Error in _process_transcribed_text: {e}", exc_info=True)
            self.reset_state()

    def _llm_clean_loop(self, text: str) -> None:
        """Execute Gemini LLM post-processing and text cleanup in a background thread.

        Args:
            text: Raw speech text to process.
        """
        cleaned = self.llm.clean_text(
            text, self.config, self.current_app_class,
            on_chunk=lambda chunk: GLib.idle_add(self.bubble.set_live_text, chunk) if self.state != "IDLE" else None
        )
        if self.state != "IDLE":
            GLib.idle_add(self.finalize_text, cleaned)

    def finalize_text(self, text: str) -> None:
        """Store dictation into SQLite history and schedule automatic paste.

        Args:
            text: Finalized (and optionally AI-cleaned) text string.
        """
        if self.state == "IDLE":
            logging.info("finalize_text called while IDLE (canceled). Aborting.")
            return

        original = getattr(self, 'last_original_text', text)
        llm_text = text if original != text else None
        self.config_manager.save_history_record(self.current_app_class, self.current_window_title, original, llm_text)

        self.current_text = text
        GLib.timeout_add(600, self.execute_paste, text, self.config.get("auto_send", False))

    def execute_paste(self, text: str, auto_send: bool) -> bool:
        """Inject dictated text into active window using wl-copy and ydotool.

        Args:
            text: Text to paste.
            auto_send: Whether to emit Enter key event after paste.

        Returns:
            Always returns False for GLib timeout removal.
        """
        suffix = " " if not auto_send else ""
        full_text = text + suffix
        self.bubble.hide()

        self.send_status = "pasting"
        self.export_state()

        def _do_paste():
            try:
                if self.config.get("restore_window_focus", False):
                    restore_window_focus(self.current_app_class, self.current_window_title)
                    time.sleep(0.15)

                wl_copy_path = shutil.which("wl-copy")
                if wl_copy_path:
                    subprocess.run([wl_copy_path], input=full_text, text=True)
                    time.sleep(0.05)
                    subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"])
                    if auto_send:
                        time.sleep(0.05)
                        subprocess.run(["ydotool", "key", "28:1", "28:0"])
                else:
                    subprocess.run(["ydotool", "type", full_text])
                    if auto_send:
                        time.sleep(0.05)
                        subprocess.run(["ydotool", "key", "28:1", "28:0"])
            except Exception as e:
                logging.error(f"Error during automatic paste: {e}", exc_info=True)
            finally:
                self.send_status = "idle"
                self.reset_state()
            return False

        GLib.timeout_add(100, _do_paste)
        return False

    def execute_copy(self) -> bool:
        """Copy current transcription buffer into system clipboard via wl-copy.

        Returns:
            Always returns False for GLib timeout removal.
        """
        wl_copy_path = shutil.which("wl-copy")
        if wl_copy_path:
            subprocess.run([wl_copy_path], input=self.current_text, text=True)
        self.reset_state()
        return False

    def reset_state(self) -> bool:
        """Reset daemon orchestrator state to IDLE and synchronize UI widgets.

        Returns:
            Always returns False for GLib idle handler removal.
        """
        logging.info("Resetting state to IDLE")
        self.media.resume_media()
        if self.bubble.window.get_realized():
            pos = self.bubble.window.get_position()
            size = self.bubble.window.get_size()
            self.config["window_x"] = pos[0]
            self.config["window_y"] = pos[1]
            self.config["window_width"] = size[0]
            self.config["window_height"] = size[1]
            self.config_manager.save_config(self.config)

        self.bubble.hide()
        self.state = "IDLE"
        self.voice_commands.reset_buffer(cooldown=1.5)
        self.tray.set_daemon_state("IDLE")
        self.tray.update_toggles(self.config.get("auto_send", False), self.config.get("ai_enabled", False))
        self.update_status(self.i18n.t("ready", self.engine.model_size))
        self.export_state()
        self._start_idle_voice_command_listener()
        return False

    def update_status(self, text: str) -> None:
        """Log state transition string.

        Args:
            text: Status description string.
        """
        logging.info(f"State Update: {text}")

    def update_timer(self) -> bool:
        """Periodic 100ms timer updating elapsed recording/cleaning time and telemetry.

        Returns:
            True to continue timer ticks, False to stop.
        """
        if self.state in ["RECORDING", "PAUSED"]:
            if self.state == "RECORDING":
                elapsed = time.time() - self.start_time - self.total_paused_time
            else:
                elapsed = self.pause_start_time - self.start_time - self.total_paused_time

            mins, secs = int(elapsed) // 60, int(elapsed) % 60
            self.last_time_str = f"{mins:02d}:{secs:02d}"
            self.export_state()
            return True
        elif self.state in ["TRANSCRIBING", "CLEANING"]:
            if hasattr(self, 'processing_start_time') and self.state == "CLEANING":
                elapsed = time.time() - self.processing_start_time
                mins, secs = int(elapsed) // 60, int(elapsed) % 60
                self.last_time_str = f"{mins:02d}:{secs:02d}"
            self.export_state()
            return True

        self.timer_id = None
        return False

    # -------------------------------------------------------------------------
    # Actions & Commands
    # -------------------------------------------------------------------------
    def action_record(self) -> None:
        """Handle primary record action (toggle between idle, recording, and finish)."""
        if self.state == "IDLE":
            self.start_recording()
        elif self.state == "PAUSED":
            self.total_paused_time += time.time() - self.pause_start_time
            self.state = "RECORDING"
            if not self.config.get("hide_bubble", False):
                self.bubble.show_recording_state(start_time=self.start_time, total_paused_time=self.total_paused_time)
            self.tray.set_daemon_state("RECORDING")
            self.export_state()
        elif self.state == "RECORDING":
            self.action_finish_normal()

    def action_pause(self) -> None:
        """Handle pause/resume toggle during active recording."""
        if self.state == "RECORDING":
            self.state = "PAUSED"
            self.pause_start_time = time.time()
            if not self.config.get("hide_bubble", False):
                self.bubble.show_paused_state(start_time=self.start_time, pause_start_time=self.pause_start_time, total_paused_time=self.total_paused_time)
            self.tray.set_daemon_state("PAUSED")
            self.export_state()
        elif self.state == "PAUSED":
            self.action_record()

    def action_cancel(self) -> None:
        """Cancel ongoing recording/processing and discard all audio data."""
        logging.info(f"Action: Cancel triggered (current state: {self.state})")
        if self.gemini_live_engine.is_active():
            threading.Thread(target=self.gemini_live_engine.stop_session, kwargs={"timeout": 0.5}, daemon=True).start()
        if self.state in ["RECORDING", "PAUSED"]:
            self.audio.stop_recording()
        self.reset_state()

    def action_send(self) -> None:
        """Finish recording and immediately stop audio capture."""
        if self.state in ["RECORDING", "PAUSED"]:
            self.next_action = "SEND"
            self.stop_recording()

    def action_finish_normal(self) -> None:
        """Finish recording explicitly without applying LLM post-processing."""
        if self.state in ["RECORDING", "PAUSED"]:
            self.next_action = "FINISH_NORMAL"
            self.stop_recording()

    def action_finish_ai(self) -> None:
        """Finish recording and force Gemini AI text cleanup."""
        if self.state in ["RECORDING", "PAUSED"]:
            self.next_action = "FINISH_AI"
            self.stop_recording()

    def action_toggle_ai(self) -> None:
        """Toggle global AI post-processing flag and notify desktop."""
        new_state = not self.config.get("ai_enabled", False)
        self.config["ai_enabled"] = new_state
        self.config_manager.save_config(self.config)
        if hasattr(self.tray, 'ai_check') and self.tray.ai_check:
            self.tray.ai_check.set_active(new_state)
        self.export_state()
        self.show_notification("OpenDictate", self.i18n.t("ai_enabled") if new_state else self.i18n.t("ai_disabled"))

    def action_toggle_autosend(self) -> None:
        """Toggle automatic Enter key emission flag upon paste."""
        new_state = not self.config.get("auto_send", False)
        self.config["auto_send"] = new_state
        self.config_manager.save_config(self.config)
        if hasattr(self.tray, 'auto_send_check') and self.tray.auto_send_check:
            self.tray.auto_send_check.set_active(new_state)
        self.export_state()
        self.show_notification("OpenDictate", self.i18n.t("autosend_enabled") if new_state else self.i18n.t("autosend_disabled"))

    def action_toggle_realtime(self) -> None:
        """Toggle real-time streaming VAD chunking transcription."""
        new_state = not self.config.get("realtime_mode", True)
        self.config["realtime_mode"] = new_state
        self.config_manager.save_config(self.config)
        self.export_state()
        self.show_notification("OpenDictate", self.i18n.t("realtime_enabled") if new_state else self.i18n.t("realtime_disabled"))

    def action_toggle_bubble(self) -> None:
        """Toggle floating GTK OSD text bubble visibility."""
        new_state = not self.config.get("hide_bubble", False)
        self.config["hide_bubble"] = new_state
        self.config_manager.save_config(self.config)
        self.export_state()
        if new_state:
            self.bubble.hide()
        self.show_notification("OpenDictate", self.i18n.t("bubble_hidden") if new_state else self.i18n.t("bubble_visible"))

    def action_cycle_model(self) -> None:
        """Cycle sequentially through available Whisper model sizes."""
        sizes = ["tiny", "base", "small", "medium", "large-v3"]
        curr = self.engine.model_size
        idx = sizes.index(curr) if curr in sizes else 0
        next_model = sizes[(idx + 1) % len(sizes)]
        if self.state == "IDLE":
            self.load_model_async(next_model)

    def on_auto_send_toggled(self, active: bool) -> None:
        """Callback triggered by tray auto-send check item toggle.

        Args:
            active: Checked boolean state.
        """
        self.config["auto_send"] = active
        self.config_manager.save_config(self.config)
        self.export_state()

    def on_ai_toggled(self, active: bool) -> None:
        """Callback triggered by tray AI cleanup check item toggle.

        Args:
            active: Checked boolean state.
        """
        self.config["ai_enabled"] = active
        self.config_manager.save_config(self.config)
        self.export_state()

    def open_config_window(self) -> None:
        """Instantiate and present the GTK settings and preferences window."""
        if self.config_window:
            self.config_window.update_ui_from_config(self.config)
            self.config_window.present()
            return

        try:
            from opendictate_config_ui import ConfigWindow
            self.config_window = ConfigWindow(
                self.config_manager.db_path,
                CONFIG_PATH,
                on_config_saved=self.on_config_saved,
                daemon_ref=self
            )
            self.config_window.connect("destroy", lambda w: setattr(self, 'config_window', None))
            self.config_window.show_all()
        except Exception as e:
            logging.error(f"Error opening config window: {e}", exc_info=True)
            self.show_notification(self.i18n.t("error"), self.i18n.t("error_opening_config"), timeout=5000)

    def on_tray_record_clicked(self) -> None:
        """Handle single primary action on system tray icon click."""
        if self.state == "IDLE":
            self.start_recording()
        else:
            if not self.config.get("hide_bubble", False):
                self.bubble.window.present()

    def open_wizard_window(self) -> None:
        """Launch the First-Run Setup & Onboarding Wizard."""
        try:
            from ui.wizard import FirstRunWizard
            self.wizard_window = FirstRunWizard(
                self.config_manager,
                on_finish=self.on_config_saved
            )
            self.wizard_window.connect("destroy", lambda w: setattr(self, 'wizard_window', None))
            self.wizard_window.present()
        except Exception as e:
            logging.error(f"Error opening wizard window: {e}", exc_info=True)

    def open_update_window(self, update_info: Optional[Dict[str, Any]] = None) -> None:
        """Instantiate and present the native GTK UpdateDialog window."""
        if self.update_window:
            self.update_window.present()
            return

        if not update_info:
            update_info = {
                "version": self.config.get("available_update_version", ""),
                "url": self.config.get("available_update_url", ""),
                "notes": self.config.get("available_update_notes", "")
            }

        if not update_info.get("version"):
            return

        try:
            from ui.update_dialog import show_update_dialog
            self.update_window = show_update_dialog(self.config, self.config_manager, update_info)
            self.update_window.connect("destroy", lambda w: setattr(self, 'update_window', None))
        except Exception as e:
            logging.error(f"Error opening update dialog: {e}", exc_info=True)

    def action_check_updates(self) -> None:
        """Trigger explicit check for updates and present dialog if update is found."""
        from core.updater import check_for_updates
        check_for_updates(
            self.config,
            self.config_manager,
            force=True,
            on_update_found=self.open_update_window
        )

    def on_config_saved(self, new_config: Optional[Dict[str, Any]] = None) -> None:
        """Reload daemon configuration, refresh UI locales, and trigger model reload if necessary.

        Args:
            new_config: Optional updated config dictionary.
        """
        old_model = self.engine.model_size
        old_device = self.engine.device
        old_compute = self.engine.compute_type
        old_threads = self.engine.cpu_threads

        if new_config is not None:
            self.config = new_config
            self.config_manager.save_config(self.config, explicit_api_key_update=True)
        else:
            self.config = self.config_manager.load_config()

        self.i18n = get_translator(self.config.get("ui_language", "en"))
        self.bubble.config = self.config
        self.bubble.i18n = self.i18n
        self.resolve_bubble_mode()

        self.tray.config = self.config
        self.tray.i18n = self.i18n
        self.tray.build_menu()

        self.voice_commands.config = self.config
        self.voice_commands.load_templates()

        if self.config.get("voice_commands_enabled", False) and not self.voice_listener_paused_by_ui:
            self._start_idle_voice_command_listener()
        else:
            self._stop_idle_voice_command_listener()

        new_model = self.config.get("whisper_model_size", old_model)
        new_device = self.config.get("whisper_device", "auto")
        new_compute = self.config.get("whisper_compute_type", "default")
        new_threads = int(self.config.get("whisper_cpu_threads", 0))

        backend_changed = (
            old_device != new_device or
            old_compute != new_compute or
            old_threads != new_threads
        )

        stt_backend = self.config.get("stt_backend", "local_whisper")
        if stt_backend == "gemini_live" and self.config.get("api_key"):
            if self.engine.model is not None:
                self.engine.unload_model()
            if self.state == "IDLE":
                self.export_state()
        elif stt_backend == "local_whisper":
            if self.engine.model is None or old_model != new_model or backend_changed:
                if self.state == "IDLE":
                    self.load_model_async(new_model)


if __name__ == "__main__":
    if "--force-start" not in sys.argv:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(SOCKET_PATH)
            s.sendall(b"settings")
            s.close()
            print("OpenDictate is already running. Opening settings window.")
            sys.exit(0)
        except Exception:
            pass

    app = DictationDaemon()
    Gtk.main()

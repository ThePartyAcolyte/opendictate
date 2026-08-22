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
import json
import time
import socket
import shutil
import logging
import threading
import subprocess
import numpy as np
import difflib
from typing import Dict, Any, Optional
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
from core.config import ConfigManager, CONFIG_PATH
from core.audio import AudioRecorder
from core.engine import WhisperEngine
from core.llm import LLMService
from core.mpris import MediaController
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
        self.llm = LLMService(self.config_manager)
        self.media = MediaController()

        self.state: str = "IDLE"
        self.next_action: Optional[str] = None
        self.last_original_text: str = ""
        self.current_text: str = ""
        self.confirmed_text: str = ""
        self.last_transcribed_time: float = 0.0

        self.start_time: float = 0.0
        self.pause_start_time: float = 0.0
        self.total_paused_time: float = 0.0
        self.processing_start_time: float = 0.0
        self.timer_id: Optional[int] = None
        self.config_window = None

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
        }
        self.ipc = IPCServer(self.ipc_handlers)
        threading.Thread(target=self.ipc.start, daemon=True).start()

        # Check first run onboarding
        if not self.config.get("initial_setup_completed", False):
            GLib.idle_add(self.open_wizard_window)

        # Initial model load
        model_size = self.config.get("whisper_model_size", "medium")
        self.load_model_async(model_size)

        # Check for updates in background
        from core.updater import check_for_updates
        check_for_updates(self.config, self.config_manager)

    # -------------------------------------------------------------------------
    # Notification & Sound Helpers
    # -------------------------------------------------------------------------
    def show_notification(self, title: str, message: str, timeout: int = 1500) -> None:
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
        if os.path.exists(sound_path):
            subprocess.Popen(["pw-play", sound_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def export_state(self) -> None:
        """Export state telemetry to /tmp/opendictate_state.json for GNOME extension / OpenDeck."""
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
        if key == "ready":
            status_text = self.i18n.t("ready", self.engine.model_size)
        else:
            status_text = self.i18n.t(key)

        state_data = {
            "state": self.state,
            "status_text": status_text,
            "ui_language": self.config.get("ui_language", "en"),
            "time_str": getattr(self, "last_time_str", "00:00"),
            "model": self.engine.model_size,
            "level": getattr(self.audio, "audio_level", 0.0),
            "ai_enabled": self.config.get("ai_enabled", False),
            "autosend_enabled": self.config.get("auto_send", False),
            "autopause_enabled": self.config.get("auto_pause_media", True),
            "realtime_enabled": self.config.get("realtime_mode", True),
            "hide_bubble": self.config.get("hide_bubble", False),
            "restore_window_focus": self.config.get("restore_window_focus", False),
            "send_status": getattr(self, "send_status", "idle"),
            "start_time": self.start_time,
            "pause_start_time": self.pause_start_time,
            "total_paused_time": self.total_paused_time
        }
        try:
            with open("/tmp/opendictate_state.json", "w") as f:
                json.dump(state_data, f)
        except Exception as e:
            logging.error(f"Error exporting state JSON: {e}")

    def quit_app(self) -> None:
        """Export OFFLINE state telemetry and exit application."""
        try:
            state_data = {"state": "OFFLINE", "status_text": "Offline"}
            with open("/tmp/opendictate_state.json", "w") as f:
                json.dump(state_data, f)
        except Exception as e:
            logging.error(f"Error exporting OFFLINE state: {e}")
        Gtk.main_quit()

    # -------------------------------------------------------------------------
    # Model Loading
    # -------------------------------------------------------------------------
    def load_model_async(self, size: str) -> None:
        """Asynchronously load specified Whisper model size with multi-tier fallback."""
        self.state = "LOADING"
        self.update_status(self.i18n.t("loading_model_param", size=size))
        self.export_state()

        def _loader():
            success, loaded_size, status_code = self.engine.load_model(size)
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
    # Recording Lifecycle
    # -------------------------------------------------------------------------
    def start_recording(self) -> None:
        """Initiate audio capture lifecycle."""
        if not self.engine.model:
            self.show_notification("OpenDictate", self.i18n.t("error_no_models_offline"))
            return

        self.current_app_class, self.current_window_title = get_active_window_info()
        self.play_sound("/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga")
        self.media.pause_media(self.config)

        self.state = "RECORDING"
        self.start_time = time.time()
        self.total_paused_time = 0
        self.pause_start_time = 0
        self.confirmed_text = ""
        self.last_transcribed_time = 0.0

        self.resolve_bubble_mode()
        if not self.config.get("hide_bubble", False):
            self.bubble.show_recording_state(start_time=self.start_time, total_paused_time=self.total_paused_time)

        self.tray.set_daemon_state("RECORDING")

        if self.timer_id:
            GLib.source_remove(self.timer_id)
        self.timer_id = GLib.timeout_add(100, self.update_timer)

        self.audio.start_recording()
        threading.Thread(target=self._audio_stream_loop, daemon=True).start()
        if self.config.get("realtime_mode", True):
            threading.Thread(target=self._streaming_transcriber_loop, daemon=True).start()

    def _audio_stream_loop(self) -> None:
        """Audio streaming thread reading PCM buffers from process stdout."""
        while self.state in ["RECORDING", "PAUSED"]:
            success = self.audio.process_stream_chunk(
                chunk_size=1024,
                is_paused=(self.state == "PAUSED"),
                on_level_update=lambda lvl: (self.export_state(), GLib.idle_add(self.bubble.update_audio_level, lvl))
            )
            if not success:
                break

    def _streaming_transcriber_loop(self) -> None:
        """Sliding-window transcription thread running during real-time recording."""
        stride = self.config.get("chunk_stride", 15.0)
        overlap = self.config.get("chunk_overlap", 2.0)
        tolerance = self.config.get("chunk_tolerance", 1.0)
        bytes_per_sec = 16000 * 2

        while self.state in ["RECORDING", "PAUSED"]:
            if self.state == "PAUSED":
                time.sleep(0.2)
                continue

            current_time = len(self.audio.audio_buffer) / bytes_per_sec
            if current_time >= self.last_transcribed_time + stride:
                chunk_start = max(0.0, self.last_transcribed_time - overlap)
                chunk_end = min(current_time, chunk_start + stride + overlap)

                start_idx = int(chunk_start * bytes_per_sec)
                end_idx = int(chunk_end * bytes_per_sec)

                chunk_bytes = bytes(self.audio.audio_buffer[start_idx:end_idx])
                if len(chunk_bytes) % 2 != 0:
                    chunk_bytes = chunk_bytes[:-1]

                try:
                    audio_int16 = np.frombuffer(chunk_bytes, dtype=np.int16)
                    audio_float32 = audio_int16.astype(np.float32) / 32768.0

                    prompt = self.confirmed_text[-200:] if self.confirmed_text else None
                    t_start = time.perf_counter()
                    segments, _ = self.engine.transcribe_chunk(audio_float32, self.config, initial_prompt=prompt)
                    t_transcribe = time.perf_counter() - t_start

                    chunk_text = ""
                    for segment in segments:
                        if segment.words:
                            for word in segment.words:
                                abs_time = chunk_start + word.start
                                if abs_time < (chunk_end - overlap):
                                    chunk_text += word.word
                        else:
                            chunk_text += segment.text
                    
                    text_to_append = self._merge_chunk_text(
                        chunk_text=chunk_text,
                        confirmed_text=self.confirmed_text,
                        segments=segments,
                        chunk_start=chunk_start,
                        last_transcribed_time=self.last_transcribed_time,
                        tolerance=tolerance,
                        chunk_end=chunk_end,
                        overlap=overlap,
                        label="streaming"
                    )
                    logging.info(f"Chunk transcribed in {t_transcribe:.2f}s | Audio len: {chunk_end - chunk_start:.2f}s | Appended chars: {len(text_to_append)}")

                    if text_to_append and self.state == "RECORDING":
                        self.confirmed_text += text_to_append
                        GLib.idle_add(self.bubble.set_live_text, self.confirmed_text)

                    if self.state == "RECORDING":
                        self.last_transcribed_time = chunk_end - overlap
                except Exception as e:
                    logging.error(f"Streaming transcription error: {e}", exc_info=True)

            time.sleep(0.5)

    def stop_recording(self) -> None:
        """Stop audio recording and initiate STT decoding."""
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

    @staticmethod
    def _merge_chunk_text(
        chunk_text: str,
        confirmed_text: str,
        segments: list,
        chunk_start: float,
        last_transcribed_time: float,
        tolerance: float,
        chunk_end: float,
        overlap: float,
        label: str = ""
    ) -> str:
        """Merge a new transcribed chunk into the confirmed text buffer.

        Uses SequenceMatcher string alignment as the primary strategy.
        Falls back to time-based word filtering when alignment fails.

        Args:
            chunk_text: Raw text from the latest transcribed chunk.
            confirmed_text: Accumulated confirmed transcription so far.
            segments: Whisper segment objects from the transcription.
            chunk_start: Start time of the chunk in seconds.
            last_transcribed_time: Time offset of last confirmed word.
            tolerance: Seconds of tolerance for time-based fallback.
            chunk_end: End time of the chunk in seconds.
            overlap: Overlap window in seconds.
            label: Log label for debugging (e.g. 'streaming' or 'final').

        Returns:
            The text fragment to append to confirmed_text.
        """
        if not confirmed_text or not chunk_text:
            return chunk_text

        search_len = min(len(confirmed_text), 150)
        suffix = confirmed_text[-search_len:].lower()
        prefix = chunk_text[:150].lower()

        matcher = difflib.SequenceMatcher(None, suffix, prefix)
        match = matcher.find_longest_match(0, len(suffix), 0, len(prefix))

        if match.size > 5 and match.b < 15:
            logging.debug(f"[{label}] Merge by string alignment (match size {match.size})")
            return chunk_text[match.b + match.size:]

        logging.debug(f"[{label}] String alignment failed, using time-based fallback")
        text_to_append = ""
        for segment in segments:
            if segment.words:
                for word in segment.words:
                    abs_time = chunk_start + word.start
                    if abs_time >= (last_transcribed_time - tolerance) and abs_time < (chunk_end - overlap):
                        text_to_append += word.word
            else:
                text_to_append += segment.text
        return text_to_append



    def _final_transcribe_loop(self) -> None:
        """Execute final transcription pass (full-batch or final chunk)."""
        try:
            bytes_per_sec = 16000 * 2
            current_audio_time = len(self.audio.audio_buffer) / bytes_per_sec

            if not self.config.get("realtime_mode", True):
                logging.info("Executing full audio batch transcription...")
                chunk_bytes = bytes(self.audio.audio_buffer)
                if len(chunk_bytes) % 2 != 0:
                    chunk_bytes = chunk_bytes[:-1]

                audio_int16 = np.frombuffer(chunk_bytes, dtype=np.int16)
                audio_float32 = audio_int16.astype(np.float32) / 32768.0

                segments, _ = self.engine.transcribe_chunk(audio_float32, self.config)
                full_text = ""
                for segment in segments:
                    full_text += segment.text
                self.confirmed_text = full_text
            else:
                overlap = self.config.get("chunk_overlap", 2.0)
                tolerance = self.config.get("chunk_tolerance", 1.0)
                if current_audio_time > self.last_transcribed_time:
                    chunk_start = max(0.0, self.last_transcribed_time - overlap)
                    start_idx = int(chunk_start * bytes_per_sec)
                    chunk_bytes = bytes(self.audio.audio_buffer[start_idx:])
                    if len(chunk_bytes) % 2 != 0:
                        chunk_bytes = chunk_bytes[:-1]

                    audio_int16 = np.frombuffer(chunk_bytes, dtype=np.int16)
                    audio_float32 = audio_int16.astype(np.float32) / 32768.0

                    prompt = self.confirmed_text[-200:] if self.confirmed_text else None
                    t_start = time.perf_counter()
                    segments, _ = self.engine.transcribe_chunk(audio_float32, self.config, initial_prompt=prompt)
                    t_transcribe = time.perf_counter() - t_start

                    chunk_text = ""
                    for segment in segments:
                        if segment.words:
                            for word in segment.words:
                                chunk_text += word.word
                        else:
                            chunk_text += segment.text

                    text_to_append = self._merge_chunk_text(
                        chunk_text=chunk_text,
                        confirmed_text=self.confirmed_text,
                        segments=segments,
                        chunk_start=chunk_start,
                        last_transcribed_time=self.last_transcribed_time,
                        tolerance=tolerance,
                        chunk_end=current_audio_time,
                        overlap=0.0,
                        label="final"
                    )
                    logging.info(f"Final chunk transcribed in {t_transcribe:.2f}s | Audio len: {current_audio_time - chunk_start:.2f}s | Appended chars: {len(text_to_append)}")
                    if text_to_append:
                        self.confirmed_text += text_to_append

            final_text = self.confirmed_text.strip()
            logging.info(f"Final transcript text: '{final_text}'")
            GLib.idle_add(self._process_transcribed_text, final_text)

        except Exception as e:
            logging.error(f"Error during final transcription: {e}", exc_info=True)
            GLib.idle_add(self.on_transcription_error, str(e))

    def _process_transcribed_text(self, text: str) -> None:
        if self.state == "IDLE":
            logging.info("Transcribed text received while IDLE (canceled). Aborting.")
            return

        if not text:
            logging.info("Transcription yielded empty text. Resetting state.")
            self.reset_state()
            return

        self.last_original_text = text

        use_llm = False
        if self.next_action == "FINISH_AI":
            use_llm = True
        elif self.next_action == "FINISH_NORMAL":
            use_llm = False
        else:
            use_llm = self.config.get("ai_enabled", False)

        if use_llm and self.config.get("api_key", "").strip():
            self.state = "CLEANING"
            self.processing_start_time = time.time()
            if not self.config.get("hide_bubble", False):
                self.bubble.show_processing_state(self.i18n.t("cleaning"))
            self.tray.set_daemon_state("CLEANING")
            self.update_status(self.i18n.t("cleaning"))
            threading.Thread(target=self._llm_clean_loop, args=(text,), daemon=True).start()
        else:
            self.finalize_text(text)

    def _llm_clean_loop(self, text: str) -> None:
        cleaned = self.llm.clean_text(
            text, self.config, self.current_app_class,
            on_chunk=lambda chunk: GLib.idle_add(self.bubble.set_live_text, chunk) if self.state != "IDLE" else None
        )
        if self.state != "IDLE":
            GLib.idle_add(self.finalize_text, cleaned)

    def finalize_text(self, text: str) -> None:
        if self.state == "IDLE":
            logging.info("finalize_text called while IDLE (canceled). Aborting.")
            return

        original = getattr(self, 'last_original_text', text)
        llm_text = text if original != text else None
        self.config_manager.save_history_record(self.current_app_class, self.current_window_title, original, llm_text)

        self.current_text = text
        GLib.timeout_add(600, self.execute_paste, text, self.config.get("auto_send", False))

    def execute_paste(self, text: str, auto_send: bool) -> bool:
        suffix = " " if not auto_send else ""
        full_text = text + suffix
        self.bubble.hide()

        self.send_status = "pasting"
        self.export_state()

        def _do_paste():
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

            self.send_status = "idle"
            self.reset_state()
            return False

        GLib.timeout_add(100, _do_paste)
        return False

    def execute_copy(self) -> bool:
        wl_copy_path = shutil.which("wl-copy")
        if wl_copy_path:
            subprocess.run([wl_copy_path], input=self.current_text, text=True)
        self.reset_state()
        return False

    def reset_state(self) -> bool:
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
        self.tray.set_daemon_state("IDLE")
        self.tray.update_toggles(self.config.get("auto_send", False), self.config.get("ai_enabled", False))
        self.update_status(self.i18n.t("ready", self.engine.model_size))
        self.export_state()
        return False

    def update_status(self, text: str) -> None:
        logging.info(f"State Update: {text}")

    def update_timer(self) -> bool:
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
        logging.info(f"Action: Cancel triggered (current state: {self.state})")
        if self.state in ["RECORDING", "PAUSED"]:
            self.audio.stop_recording()
        self.reset_state()

    def action_send(self) -> None:
        if self.state in ["RECORDING", "PAUSED"]:
            self.next_action = "SEND"
            self.stop_recording()

    def action_finish_normal(self) -> None:
        if self.state in ["RECORDING", "PAUSED"]:
            self.next_action = "FINISH_NORMAL"
            self.stop_recording()

    def action_finish_ai(self) -> None:
        if self.state in ["RECORDING", "PAUSED"]:
            self.next_action = "FINISH_AI"
            self.stop_recording()

    def action_toggle_ai(self) -> None:
        new_state = not self.config.get("ai_enabled", False)
        self.config["ai_enabled"] = new_state
        self.config_manager.save_config(self.config)
        if hasattr(self.tray, 'ai_check') and self.tray.ai_check:
            self.tray.ai_check.set_active(new_state)
        self.export_state()
        self.show_notification("OpenDictate", self.i18n.t("ai_enabled") if new_state else self.i18n.t("ai_disabled"))

    def action_toggle_autosend(self) -> None:
        new_state = not self.config.get("auto_send", False)
        self.config["auto_send"] = new_state
        self.config_manager.save_config(self.config)
        if hasattr(self.tray, 'auto_send_check') and self.tray.auto_send_check:
            self.tray.auto_send_check.set_active(new_state)
        self.export_state()
        self.show_notification("OpenDictate", self.i18n.t("autosend_enabled") if new_state else self.i18n.t("autosend_disabled"))

    def action_toggle_realtime(self) -> None:
        new_state = not self.config.get("realtime_mode", True)
        self.config["realtime_mode"] = new_state
        self.config_manager.save_config(self.config)
        self.export_state()
        self.show_notification("OpenDictate", self.i18n.t("realtime_enabled") if new_state else self.i18n.t("realtime_disabled"))

    def action_toggle_bubble(self) -> None:
        new_state = not self.config.get("hide_bubble", False)
        self.config["hide_bubble"] = new_state
        self.config_manager.save_config(self.config)
        self.export_state()
        if new_state:
            self.bubble.hide()
        self.show_notification("OpenDictate", self.i18n.t("bubble_hidden") if new_state else self.i18n.t("bubble_visible"))

    def action_cycle_model(self) -> None:
        sizes = ["tiny", "base", "small", "medium", "large-v3"]
        curr = self.engine.model_size
        idx = sizes.index(curr) if curr in sizes else 0
        next_model = sizes[(idx + 1) % len(sizes)]
        if self.state == "IDLE":
            self.load_model_async(next_model)

    def on_auto_send_toggled(self, active: bool) -> None:
        self.config["auto_send"] = active
        self.config_manager.save_config(self.config)
        self.export_state()

    def on_ai_toggled(self, active: bool) -> None:
        self.config["ai_enabled"] = active
        self.config_manager.save_config(self.config)
        self.export_state()

    def open_config_window(self) -> None:
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
            # If already active, simply ensure the control bubble is visible without toggling state
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

    def on_config_saved(self, new_config: Optional[Dict[str, Any]] = None) -> None:
        old_model = self.engine.model_size
        if new_config is not None:
            self.config = new_config
            self.config_manager.save_config(self.config)
        else:
            self.config = self.config_manager.load_config()

        self.i18n = get_translator(self.config.get("ui_language", "en"))
        self.bubble.config = self.config
        self.bubble.i18n = self.i18n
        self.resolve_bubble_mode()

        self.tray.config = self.config
        self.tray.i18n = self.i18n
        self.tray.build_menu()

        self.export_state()
        new_model = self.config.get("whisper_model_size")
        if old_model and new_model and old_model != new_model and self.state == "IDLE":
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

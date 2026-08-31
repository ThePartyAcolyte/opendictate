"""
Interactive Multi-Sample Voice Phrase Recorder & Live Calibrator Dialog for OpenDictate.

Allows naming trigger phrases, recording an arbitrary number of acoustic samples (N >= 1),
tuning individual detection thresholds with automatic optimal threshold suggestion,
and performing real-time Cosine DTW live verification.
"""

import os
import time
import socket
import signal
import logging
import subprocess
import threading
from typing import Optional, Callable, Any, List

import numpy as np

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from i18n import get_translator
from core.aec import EchoCancelManager
from core.voice_commands import (
    VoiceCommandManager,
    PhraseTemplate,
    trim_silence_vad,
    compute_dtw_similarity,
    compute_recommended_threshold
)
from core.ipc import SOCKET_PATH


RECORDER_CSS = b"""
window.sample-recorder-window {
    background-color: #1e1e1e;
    color: #e0e0e0;
}

.recorder-header {
    background-color: #161616;
    padding: 16px 20px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.recorder-title {
    font-size: 15px;
    font-weight: 700;
    color: #ffffff;
}

.recorder-subtitle {
    font-size: 12px;
    color: #a0a0a0;
}

.recorder-content {
    padding: 16px 20px;
}

.status-card {
    background-color: #242424;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 8px;
}

.phrase-name-entry {
    background-color: #181818;
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
}

.sample-badge {
    font-size: 13px;
    font-weight: 700;
    color: #ff9800;
}

.btn-primary-action {
    background-color: #e65100;
    color: #ffffff;
    font-weight: 700;
    border-radius: 6px;
    padding: 8px 18px;
    border: none;
}

.btn-primary-action:hover {
    background-color: #f57c00;
}

.btn-secondary-action {
    background-color: rgba(255, 255, 255, 0.08);
    color: #e0e0e0;
    font-weight: 600;
    border-radius: 6px;
    padding: 8px 14px;
    border: 1px solid rgba(255, 255, 255, 0.12);
}

.btn-secondary-action:hover {
    background-color: rgba(255, 255, 255, 0.15);
    color: #ffffff;
}

.btn-suggest-th {
    background-color: #0277bd;
    color: #ffffff;
    font-weight: 600;
    border-radius: 6px;
    padding: 6px 12px;
    border: none;
}

.btn-suggest-th:hover {
    background-color: #0288d1;
}

.recorder-footer {
    background-color: #161616;
    padding: 14px 20px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
}
"""


class SampleRecorderDialog(Gtk.Window):
    """Modal dialog for enrolling multi-sample trigger phrases with per-phrase thresholds."""

    def __init__(
        self,
        parent: Gtk.Window,
        action: str,
        action_display_name: str,
        voice_commands: VoiceCommandManager,
        aec_manager: EchoCancelManager,
        phrase: Optional[PhraseTemplate] = None,
        ui_language: str = "es",
        on_saved: Optional[Callable[[], None]] = None
    ) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title("OpenDictate")
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.set_default_size(540, 520)
        self.set_resizable(False)
        self.get_style_context().add_class("sample-recorder-window")

        self.action = action
        self.action_display_name = action_display_name
        self.voice_commands = voice_commands
        self.aec_manager = aec_manager
        self.i18n = get_translator(ui_language)
        self.on_saved = on_saved

        # Target phrase being edited/created
        if phrase:
            self.phrase = phrase
            self.is_new_phrase = False
        else:
            # New phrase with default name
            default_name = self.voice_commands.DEFAULT_ACTION_NAMES.get(action, action)
            self.phrase = PhraseTemplate(
                id=str(time.time()).replace(".", "")[-8:],
                name=default_name,
                threshold=0.75,
                samples=[]
            )
            self.is_new_phrase = True

        # Working copy of sample sequences
        self.enrolled_samples: List[np.ndarray] = list(self.phrase.samples)

        self.is_recording = False
        self.record_proc: Optional[subprocess.Popen] = None
        self.recorded_pcm_chunks: List[bytes] = []

        self.test_thread_running = False
        self.test_proc: Optional[subprocess.Popen] = None

        self._apply_css()
        self._build_ui()
        self.connect("delete-event", self._on_close)

        # Notify daemon to pause idle listening while modal is open
        self._send_daemon_ipc("pause-voice-listener")

        self._sync_ui_state()

    def _apply_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(RECORDER_CSS)
        self.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _send_daemon_ipc(self, cmd: str) -> None:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(SOCKET_PATH)
            s.sendall(cmd.encode("utf-8"))
            s.close()
        except Exception:
            pass

    def _build_ui(self) -> None:
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main_vbox)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        header.get_style_context().add_class("recorder-header")
        title = Gtk.Label(
            label=f"🎙️ Configurar Frase: {self.action_display_name}",
            xalign=0
        )
        title.get_style_context().add_class("recorder-title")
        header.pack_start(title, False, False, 0)

        subtitle = Gtk.Label(
            label="Grabe tantas muestras como desee para esta palabra clave y calibre su umbral individual.",
            xalign=0
        )
        subtitle.get_style_context().add_class("recorder-subtitle")
        header.pack_start(subtitle, False, False, 0)
        main_vbox.pack_start(header, False, False, 0)

        # Content
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.get_style_context().add_class("recorder-content")

        # Card 1: Phrase Name
        c_name = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        c_name.get_style_context().add_class("status-card")
        lbl_pname = Gtk.Label(label="Nombre / Frase:", xalign=0)
        lbl_pname.set_size_request(130, -1)
        c_name.pack_start(lbl_pname, False, False, 0)

        self.entry_phrase_name = Gtk.Entry()
        self.entry_phrase_name.set_text(self.phrase.name)
        self.entry_phrase_name.get_style_context().add_class("phrase-name-entry")
        self.entry_phrase_name.set_hexpand(True)
        c_name.pack_start(self.entry_phrase_name, True, True, 0)
        content.pack_start(c_name, False, False, 0)

        # Card 2: Recording Samples Panel
        card_rec = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card_rec.get_style_context().add_class("status-card")

        self.lbl_rec_status = Gtk.Label(label="Listo para grabar muestras", xalign=0.5)
        self.lbl_rec_status.get_style_context().add_class("recorder-title")
        card_rec.pack_start(self.lbl_rec_status, False, False, 0)

        self.lbl_sample_badge = Gtk.Label(label="", xalign=0.5)
        self.lbl_sample_badge.get_style_context().add_class("sample-badge")
        card_rec.pack_start(self.lbl_sample_badge, False, False, 0)

        self.level_bar = Gtk.ProgressBar()
        self.level_bar.set_fraction(0.0)
        card_rec.pack_start(self.level_bar, False, False, 4)

        hbox_rec_ctrl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.btn_rec_sample = Gtk.Button(label="🎙️ Grabar Muestra")
        self.btn_rec_sample.get_style_context().add_class("btn-primary-action")
        self.btn_rec_sample.connect("clicked", self._on_record_sample_clicked)
        hbox_rec_ctrl.pack_start(self.btn_rec_sample, True, True, 0)

        self.btn_clear_samples = Gtk.Button(label="🔄 Reiniciar")
        self.btn_clear_samples.get_style_context().add_class("btn-secondary-action")
        self.btn_clear_samples.connect("clicked", self._on_clear_samples_clicked)
        hbox_rec_ctrl.pack_start(self.btn_clear_samples, False, False, 0)
        card_rec.pack_start(hbox_rec_ctrl, False, False, 0)

        content.pack_start(card_rec, False, False, 0)

        # Card 3: Per-Phrase Threshold Tuning
        card_th = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card_th.get_style_context().add_class("status-card")

        hbox_th_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_th = Gtk.Label(label="Umbral Individual de Reconocimiento:", xalign=0)
        lbl_th.get_style_context().add_class("recorder-title")
        hbox_th_hdr.pack_start(lbl_th, True, True, 0)

        self.btn_suggest_th = Gtk.Button(label="🎯 Sugerir Umbral")
        self.btn_suggest_th.get_style_context().add_class("btn-suggest-th")
        self.btn_suggest_th.connect("clicked", self._on_suggest_threshold_clicked)
        hbox_th_hdr.pack_end(self.btn_suggest_th, False, False, 0)
        card_th.pack_start(hbox_th_hdr, False, False, 0)

        self.scale_phrase_th = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.50, 0.95, 0.01)
        self.scale_phrase_th.set_value(float(self.phrase.threshold))
        self.scale_phrase_th.set_digits(2)
        self.scale_phrase_th.set_hexpand(True)
        card_th.pack_start(self.scale_phrase_th, False, False, 0)

        content.pack_start(card_th, False, False, 0)

        # Card 4: Real-time Live Verification Test
        card_test = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card_test.get_style_context().add_class("status-card")

        self.lbl_test_title = Gtk.Label(label="🧪 Prueba en Vivo", xalign=0)
        self.lbl_test_title.get_style_context().add_class("recorder-title")
        card_test.pack_start(self.lbl_test_title, False, False, 0)

        self.lbl_test_result = Gtk.Label(label="Pronuncie la frase frente al micrófono para probar.", xalign=0)
        self.lbl_test_result.get_style_context().add_class("recorder-subtitle")
        card_test.pack_start(self.lbl_test_result, False, False, 0)

        self.test_bar = Gtk.ProgressBar()
        self.test_bar.set_fraction(0.0)
        card_test.pack_start(self.test_bar, False, False, 4)

        content.pack_start(card_test, False, False, 0)
        main_vbox.pack_start(content, True, True, 0)

        # Footer
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        footer.get_style_context().add_class("recorder-footer")

        btn_cancel = Gtk.Button(label="Cancelar")
        btn_cancel.get_style_context().add_class("btn-secondary-action")
        btn_cancel.connect("clicked", lambda b: self.destroy())
        footer.pack_start(btn_cancel, False, False, 0)

        self.btn_save = Gtk.Button(label="✅ Guardar Frase")
        self.btn_save.get_style_context().add_class("btn-primary-action")
        self.btn_save.connect("clicked", self._on_save_clicked)
        footer.pack_end(self.btn_save, False, False, 0)

        main_vbox.pack_start(footer, False, False, 0)

    def _sync_ui_state(self) -> None:
        count = len(self.enrolled_samples)
        if count == 0:
            self.lbl_sample_badge.set_label("0 muestras grabadas")
            self.lbl_rec_status.set_label("Presione 'Grabar Muestra' para iniciar.")
            self.btn_rec_sample.set_label("🎙️ Grabar Muestra 1")
            self.btn_suggest_th.set_sensitive(False)
            self._stop_test_listener()
        else:
            self.lbl_sample_badge.set_label(f"✅ {count} muestra(s) registradas")
            self.lbl_rec_status.set_label(f"Muestras listas ({count}). Puede agregar más o probar.")
            self.btn_rec_sample.set_label(f"🎙️ Grabar Muestra {count + 1}")
            self.btn_suggest_th.set_sensitive(True)
            self._start_test_listener()

    def _on_record_sample_clicked(self, btn: Gtk.Button) -> None:
        if not self.is_recording:
            self._start_capture()
        else:
            self._stop_capture_and_enroll()

    def _start_capture(self) -> None:
        self._stop_test_listener()
        self.is_recording = True
        self.recorded_pcm_chunks = []
        self.btn_rec_sample.set_label("⏹️ Continuar (Terminar muestra)")
        self.lbl_rec_status.set_label("🎙️ Grabando... Pronuncie la frase y presione Continuar.")
        self.btn_save.set_sensitive(False)
        self.btn_clear_samples.set_sensitive(False)

        def _worker():
            dev = self.aec_manager.get_preferred_capture_device()
            cmd = ["arecord", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", "16000"]
            if dev and dev != "default":
                cmd.extend(["-D", dev])

            try:
                self.record_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                while self.is_recording and self.record_proc and self.record_proc.stdout:
                    chunk = self.record_proc.stdout.read(1024)
                    if not chunk:
                        break
                    self.recorded_pcm_chunks.append(chunk)
                    pcm = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                    rms = float(np.sqrt(np.mean(pcm ** 2)))
                    GLib.idle_add(self.level_bar.set_fraction, min(1.0, rms * 3.0))
            except Exception as e:
                logging.error(f"Sample capture error: {e}")
            finally:
                if self.record_proc:
                    proc = self.record_proc
                    self.record_proc = None
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                        proc.wait(timeout=0.2)
                    except Exception:
                        try:
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        except Exception:
                            pass

        threading.Thread(target=_worker, daemon=True).start()

    def _stop_capture_and_enroll(self) -> None:
        self.is_recording = False
        if self.record_proc:
            proc = self.record_proc
            self.record_proc = None
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=0.2)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass

        self.btn_save.set_sensitive(True)
        self.btn_clear_samples.set_sensitive(True)
        self.level_bar.set_fraction(0.0)

        full_pcm = b"".join(self.recorded_pcm_chunks)
        self.recorded_pcm_chunks = []

        if not full_pcm or len(full_pcm) < 1600:
            self.lbl_rec_status.set_label("⚠️ Audio muy corto o inaudible.")
            self._sync_ui_state()
            return

        samples = np.frombuffer(full_pcm, dtype=np.int16).astype(np.float32) / 32768.0
        vad_th = self.voice_commands.get_vad_threshold()

        rms = np.sqrt(np.mean(samples ** 2))
        if rms < (vad_th * 0.4):
            self.lbl_rec_status.set_label("⚠️ Nivel muy bajo. Hable más cerca del micrófono.")
            self._sync_ui_state()
            return

        trimmed = trim_silence_vad(samples, sample_rate=16000, threshold_rms=vad_th)
        if len(trimmed) < 2400:
            trimmed = samples

        seq = self.voice_commands.extractor.extract_mfcc_sequence(trimmed)
        if len(seq) < 5:
            self.lbl_rec_status.set_label("⚠️ Error al extraer características.")
            self._sync_ui_state()
            return

        self.enrolled_samples.append(seq)
        dur = len(trimmed) / 16000.0
        self.lbl_rec_status.set_label(f"✅ Muestra {len(self.enrolled_samples)} guardada ({dur:.2f}s).")

        # Auto-update suggested threshold if we have >= 2 samples
        if len(self.enrolled_samples) >= 2:
            sug = compute_recommended_threshold(self.enrolled_samples)
            self.scale_phrase_th.set_value(sug)

        self._sync_ui_state()

    def _on_clear_samples_clicked(self, btn: Gtk.Button) -> None:
        self._stop_test_listener()
        self.enrolled_samples.clear()
        self.test_bar.set_fraction(0.0)
        self.lbl_test_result.set_label("Muestras reiniciadas.")
        self._sync_ui_state()

    def _on_suggest_threshold_clicked(self, btn: Gtk.Button) -> None:
        sug = compute_recommended_threshold(self.enrolled_samples)
        self.scale_phrase_th.set_value(sug)
        self.lbl_rec_status.set_label(f"🎯 Umbral sugerido automáticamente: {sug:.2f}")

    def _start_test_listener(self) -> None:
        if self.test_thread_running or not self.enrolled_samples:
            return

        self.test_thread_running = True

        def _test_worker():
            dev = self.aec_manager.get_preferred_capture_device()
            cmd = ["arecord", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", "16000"]
            if dev and dev != "default":
                cmd.extend(["-D", dev])

            ring_buffer = np.zeros(19200, dtype=np.float32)
            vad_th = self.voice_commands.get_vad_threshold()

            try:
                self.test_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                while self.test_thread_running and self.test_proc and self.test_proc.stdout:
                    chunk = self.test_proc.stdout.read(1024)
                    if not chunk:
                        break

                    samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                    n = len(samples)
                    ring_buffer = np.roll(ring_buffer, -n)
                    ring_buffer[-n:] = samples

                    rms = np.sqrt(np.mean(ring_buffer[-8000:] ** 2))
                    if rms < vad_th:
                        def _reset_test():
                            if self.test_thread_running:
                                self.test_bar.set_fraction(0.0)
                                self.lbl_test_result.set_label("Esperando voz...")
                            return False
                        GLib.idle_add(_reset_test)
                        continue

                    active = trim_silence_vad(ring_buffer, sample_rate=16000, threshold_rms=vad_th)
                    if len(active) < 2400:
                        continue

                    live_seq = self.voice_commands.extractor.extract_mfcc_sequence(active)
                    if len(live_seq) < 5:
                        continue

                    sims = []
                    for ref_seq in self.enrolled_samples:
                        len_ratio = len(live_seq) / max(1, len(ref_seq))
                        if len_ratio < 0.55 or len_ratio > 1.80:
                            continue
                        sims.append(compute_dtw_similarity(live_seq, ref_seq))

                    sim = max(sims) if sims else 0.0

                    def _update_ui(score: float):
                        if not self.test_thread_running:
                            return False
                        self.test_bar.set_fraction(min(1.0, score))
                        current_target_th = self.scale_phrase_th.get_value()
                        if score >= current_target_th:
                            self.lbl_test_result.set_label(f"🎉 ¡Frase Reconocida! ({int(score * 100)}% >= {int(current_target_th * 100)}%)")
                        else:
                            self.lbl_test_result.set_label(f"🎙️ Similitud: {int(score * 100)}% (Umbral: {int(current_target_th * 100)}%)")
                        return False

                    GLib.idle_add(_update_ui, sim)

            except Exception as e:
                logging.debug(f"Live test listener ended: {e}")
            finally:
                if self.test_proc:
                    proc = self.test_proc
                    self.test_proc = None
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                        proc.wait(timeout=0.2)
                    except Exception:
                        try:
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        except Exception:
                            pass

        threading.Thread(target=_test_worker, daemon=True).start()

    def _stop_test_listener(self) -> None:
        self.test_thread_running = False
        if self.test_proc:
            proc = self.test_proc
            self.test_proc = None
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=0.2)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass

    def _on_save_clicked(self, btn: Gtk.Button) -> None:
        phrase_name = self.entry_phrase_name.get_text().strip() or self.phrase.name
        threshold = round(self.scale_phrase_th.get_value(), 2)

        self.phrase.name = phrase_name
        self.phrase.threshold = threshold
        self.phrase.samples = list(self.enrolled_samples)

        # Update manager
        phrases = self.voice_commands.get_phrases_for_action(self.action)
        if self.is_new_phrase:
            phrases.append(self.phrase)
        else:
            for idx, p in enumerate(phrases):
                if p.id == self.phrase.id:
                    phrases[idx] = self.phrase
                    break

        self.voice_commands.save_templates()

        self._stop_test_listener()
        self._send_daemon_ipc("resume-voice-listener")
        self._send_daemon_ipc("reload-config")

        if self.on_saved:
            self.on_saved()

        self.destroy()

    def _on_close(self, widget: Any, event: Any) -> bool:
        self.is_recording = False
        self._stop_test_listener()
        if self.record_proc:
            proc = self.record_proc
            self.record_proc = None
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=0.2)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass
        self._send_daemon_ipc("resume-voice-listener")
        return False

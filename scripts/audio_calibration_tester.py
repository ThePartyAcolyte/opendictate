#!/usr/bin/env python3
"""
OpenDictate - Standalone Audio & VAD Calibration Diagnostic Tool.

Monitors real-time microphone input, computes energy (RMS / dBFS),
tracks adaptive noise floor, provides room silence auto-calibration,
and visualizes VAD state transitions with detailed live logging.
"""

import os
import sys
import time
import queue
import logging
import datetime
import subprocess
import threading
from typing import Optional, List

import numpy as np

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib


CSS_DATA = b"""
window.calibrator-window {
    background-color: #1a1a1a;
    color: #e0e0e0;
}

.header-panel {
    background-color: #121212;
    padding: 16px 20px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.header-title {
    font-size: 16px;
    font-weight: 700;
    color: #ffffff;
}

.header-subtitle {
    font-size: 12px;
    color: #9e9e9e;
}

.card {
    background-color: #242424;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 10px;
}

.vad-banner-silence {
    background-color: #333333;
    color: #9e9e9e;
    font-size: 18px;
    font-weight: 800;
    border-radius: 6px;
    padding: 12px;
}

.vad-banner-speech {
    background-color: #2e7d32;
    color: #ffffff;
    font-size: 18px;
    font-weight: 800;
    border-radius: 6px;
    padding: 12px;
}

.metrics-label {
    font-family: monospace;
    font-size: 13px;
    color: #e0e0e0;
}

.btn-calibrate {
    background-color: #e65100;
    color: #ffffff;
    font-weight: 700;
    border-radius: 6px;
    padding: 8px 16px;
    border: none;
}

.btn-calibrate:hover {
    background-color: #f57c00;
}

.log-view {
    font-family: monospace;
    font-size: 11px;
    background-color: #141414;
    color: #b0bec5;
    padding: 8px;
}
"""


class AudioCalibrationTester(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="OpenDictate - Calibrador de Audio y VAD")
        self.set_default_size(680, 720)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.get_style_context().add_class("calibrator-window")

        # Audio parameters
        self.sample_rate = 16000
        self.chunk_samples = 512  # 32ms
        self.running = True

        # Acoustic State
        self.current_rms = 0.0
        self.current_dbfs = -90.0
        self.noise_floor_rms = 0.003
        self.user_threshold_rms = 0.015
        self.snr_db = 0.0
        self.is_speech_active = False
        self.speech_start_time = 0.0
        self.peak_speech_rms = 0.0

        # VAD Debounce (Frames)
        self.consecutive_speech_frames = 0
        self.consecutive_silence_frames = 0
        self.min_speech_frames = 2     # ~64ms
        self.hangover_silence_frames = 8  # ~256ms

        # Calibration state
        self.is_calibrating = False
        self.calibration_samples: List[float] = []

        self._apply_css()
        self._build_ui()
        self.connect("destroy", self._on_destroy)

        # Start audio thread
        self.audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self.audio_thread.start()

        # UI update timer (25 Hz = 40ms)
        GLib.timeout_add(40, self._update_ui_tick)

        self._log("Iniciando herramienta de diagnóstico de audio...")

    def _apply_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS_DATA)
        self.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _build_ui(self) -> None:
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main_vbox)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        header.get_style_context().add_class("header-panel")
        title = Gtk.Label(label="🎙️ Diagnóstico Acústico y Calibrador VAD", xalign=0)
        title.get_style_context().add_class("header-title")
        subtitle = Gtk.Label(
            label="Monitorea el nivel real de su micrófono, mide el ruido base y calibra la detección de voz.",
            xalign=0
        )
        subtitle.get_style_context().add_class("header-subtitle")
        header.pack_start(title, False, False, 0)
        header.pack_start(subtitle, False, False, 0)
        main_vbox.pack_start(header, False, False, 0)

        # Content container
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        main_vbox.pack_start(content, True, True, 0)

        # Card 1: VAD Status Banner
        vad_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vad_card.get_style_context().add_class("card")

        self.vad_banner = Gtk.Label(label="[ SILENCIO ]")
        self.vad_banner.get_style_context().add_class("vad-banner-silence")
        vad_card.pack_start(self.vad_banner, False, False, 0)

        self.vad_detail_lbl = Gtk.Label(label="Duración actual: 0.0s | Pico RMS: 0.0000", xalign=0.5)
        vad_card.pack_start(self.vad_detail_lbl, False, False, 0)
        content.pack_start(vad_card, False, False, 0)

        # Card 2: Live Metrics & Vumeter
        metrics_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        metrics_card.get_style_context().add_class("card")

        m_title = Gtk.Label(label="📊 Niveles en Tiempo Real", xalign=0)
        m_title.get_style_context().add_class("header-title")
        metrics_card.pack_start(m_title, False, False, 0)

        self.level_bar = Gtk.ProgressBar()
        self.level_bar.set_fraction(0.0)
        metrics_card.pack_start(self.level_bar, False, False, 0)

        self.metrics_lbl = Gtk.Label(
            label="RMS: 0.0000 (-90.0 dBFS) | Ruido Base: 0.0000 | SNR: +0.0 dB",
            xalign=0
        )
        self.metrics_lbl.get_style_context().add_class("metrics-label")
        metrics_card.pack_start(self.metrics_lbl, False, False, 0)
        content.pack_start(metrics_card, False, False, 0)

        # Card 3: Calibration & Threshold Control
        calib_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        calib_card.get_style_context().add_class("card")

        c_title = Gtk.Label(label="⚙️ Calibración de Ruido y Sensibilidad", xalign=0)
        c_title.get_style_context().add_class("header-title")
        calib_card.pack_start(c_title, False, False, 0)

        hbox_calib = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.btn_calibrate = Gtk.Button(label="🎯 Calibrar Ruido Ambiental (2 seg en silencio)")
        self.btn_calibrate.get_style_context().add_class("btn-calibrate")
        self.btn_calibrate.connect("clicked", self._on_calibrate_clicked)
        hbox_calib.pack_start(self.btn_calibrate, False, False, 0)

        self.calib_status_lbl = Gtk.Label(label="Listo para calibrar", xalign=0)
        hbox_calib.pack_start(self.calib_status_lbl, True, True, 0)
        calib_card.pack_start(hbox_calib, False, False, 0)

        # Slider: Threshold RMS
        hbox_slider = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        slider_lbl = Gtk.Label(label="Umbral RMS de Voz:", xalign=0)
        slider_lbl.set_size_request(160, -1)
        hbox_slider.pack_start(slider_lbl, False, False, 0)

        self.adj_threshold = Gtk.Adjustment(value=0.015, lower=0.001, upper=0.100, step_increment=0.001, page_increment=0.005)
        self.scale_threshold = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.adj_threshold)
        self.scale_threshold.set_digits(4)
        self.scale_threshold.set_value_pos(Gtk.PositionType.RIGHT)
        self.scale_threshold.connect("value-changed", self._on_threshold_changed)
        hbox_slider.pack_start(self.scale_threshold, True, True, 0)
        calib_card.pack_start(hbox_slider, False, False, 0)

        content.pack_start(calib_card, False, False, 0)

        # Card 4: Event Logs
        log_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        log_card.get_style_context().add_class("card")

        hbox_log_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        log_title = Gtk.Label(label="📝 Registro de Eventos (Log)", xalign=0)
        log_title.get_style_context().add_class("header-title")
        hbox_log_hdr.pack_start(log_title, True, True, 0)

        btn_clear_log = Gtk.Button(label="Limpiar")
        btn_clear_log.connect("clicked", lambda b: self.log_buffer.set_text(""))
        hbox_log_hdr.pack_end(btn_clear_log, False, False, 0)

        btn_save_log = Gtk.Button(label="Guardar Log")
        btn_save_log.connect("clicked", self._on_save_log)
        hbox_log_hdr.pack_end(btn_save_log, False, False, 0)

        log_card.pack_start(hbox_log_hdr, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_size_request(-1, 180)

        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.get_style_context().add_class("log-view")
        self.log_buffer = self.log_view.get_buffer()
        scroll.add(self.log_view)
        log_card.pack_start(scroll, True, True, 0)

        content.pack_start(log_card, True, True, 0)

    def _log(self, message: str) -> None:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted = f"[{timestamp}] {message}\n"
        GLib.idle_add(self._append_log_text, formatted)

    def _append_log_text(self, text: str) -> bool:
        end_iter = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end_iter, text)
        # Auto scroll to bottom
        mark = self.log_buffer.create_mark(None, self.log_buffer.get_end_iter(), False)
        self.log_view.scroll_to_mark(mark, 0.05, True, 0.0, 1.0)
        return False

    def _on_threshold_changed(self, scale: Gtk.Scale) -> None:
        self.user_threshold_rms = self.scale_threshold.get_value()
        self._log(f"Umbral RMS manual ajustado a: {self.user_threshold_rms:.4f}")

    def _on_calibrate_clicked(self, btn: Gtk.Button) -> None:
        if self.is_calibrating:
            return
        self.is_calibrating = True
        self.calibration_samples = []
        self.btn_calibrate.set_sensitive(False)
        self.calib_status_lbl.set_label("⏳ Calibrando silencio de sala... por favor no hable...")
        self._log(">>> INICIANDO CALIBRACIÓN DE RUIDO AMBIENTAL (2.0 segundos de silencio)...")

        def _calib_timer():
            time.sleep(2.0)
            GLib.idle_add(self._finish_calibration)

        threading.Thread(target=_calib_timer, daemon=True).start()

    def _finish_calibration(self) -> bool:
        self.is_calibrating = False
        self.btn_calibrate.set_sensitive(True)

        if not self.calibration_samples:
            self.calib_status_lbl.set_label("⚠️ Error al capturar muestras")
            return False

        samples_arr = np.array(self.calibration_samples)
        mean_noise = float(np.mean(samples_arr))
        std_noise = float(np.std(samples_arr))
        max_noise = float(np.max(samples_arr))

        self.noise_floor_rms = mean_noise
        # Optimal speech threshold: max noise + 3*std (or at least 2x mean noise)
        optimal_threshold = max(mean_noise * 2.2, max_noise + 2.5 * std_noise, 0.006)

        self.user_threshold_rms = optimal_threshold
        self.scale_threshold.set_value(optimal_threshold)

        result_msg = f"✅ Calibrado: Piso={mean_noise:.4f} (Max={max_noise:.4f}) | Umbral recomendado={optimal_threshold:.4f}"
        self.calib_status_lbl.set_label(result_msg)
        self._log(f"RESULTADO CALIBRACIÓN: {result_msg}")
        return False

    def _on_save_log(self, btn: Gtk.Button) -> None:
        start_iter = self.log_buffer.get_start_iter()
        end_iter = self.log_buffer.get_end_iter()
        log_text = self.log_buffer.get_text(start_iter, end_iter, True)
        target = "/tmp/opendictate_audio_debug.log"
        try:
            with open(target, "w") as f:
                f.write(log_text)
            self._log(f"Log guardado exitosamente en: {target}")
        except Exception as e:
            self._log(f"Error al guardar log: {e}")

    def _audio_loop(self) -> None:
        """Continuous audio capture loop using arecord."""
        cmd = ["arecord", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", str(self.sample_rate)]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self._log("Captura iniciada vía arecord (16kHz S16_LE mono).")
            bytes_per_chunk = self.chunk_samples * 2

            while self.running and proc and proc.stdout:
                raw_chunk = proc.stdout.read(bytes_per_chunk)
                if not raw_chunk:
                    break

                samples = np.frombuffer(raw_chunk, dtype=np.int16).astype(np.float32) / 32768.0
                rms = float(np.sqrt(np.mean(samples ** 2)))
                dbfs = 20.0 * np.log10(max(rms, 1e-6))

                self.current_rms = rms
                self.current_dbfs = dbfs

                if self.is_calibrating:
                    self.calibration_samples.append(rms)

                # Adaptive noise floor tracking (when not speaking)
                if not self.is_speech_active and rms < self.noise_floor_rms * 1.5:
                    self.noise_floor_rms = 0.95 * self.noise_floor_rms + 0.05 * rms

                # SNR in dB
                snr = 20.0 * np.log10(max(rms, 1e-6) / max(self.noise_floor_rms, 1e-6))
                self.snr_db = snr

                # VAD State Machine
                is_above_threshold = rms >= self.user_threshold_rms

                if is_above_threshold:
                    self.consecutive_speech_frames += 1
                    self.consecutive_silence_frames = 0
                else:
                    self.consecutive_silence_frames += 1
                    self.consecutive_speech_frames = 0

                if not self.is_speech_active:
                    if self.consecutive_speech_frames >= self.min_speech_frames:
                        self.is_speech_active = True
                        self.speech_start_time = time.time()
                        self.peak_speech_rms = rms
                        self._log(f"🟢 VAD: INICIO DE VOZ (RMS: {rms:.4f}, dBFS: {dbfs:.1f} dB, SNR: +{snr:.1f} dB)")
                else:
                    if rms > self.peak_speech_rms:
                        self.peak_speech_rms = rms

                    if self.consecutive_silence_frames >= self.hangover_silence_frames:
                        self.is_speech_active = False
                        dur = time.time() - self.speech_start_time
                        self._log(f"🔴 VAD: FIN DE VOZ (Duración: {dur:.2f}s, Pico RMS: {self.peak_speech_rms:.4f})")

        except Exception as e:
            self._log(f"Error en bucle de audio: {e}")
        finally:
            if proc:
                try:
                    proc.terminate()
                    proc.kill()
                except Exception:
                    pass

    def _update_ui_tick(self) -> bool:
        if not self.running:
            return False

        # Update Level Bar
        frac = min(1.0, self.current_rms * 5.0)
        self.level_bar.set_fraction(frac)

        # Update Metrics Label
        self.metrics_lbl.set_label(
            f"RMS: {self.current_rms:.4f} ({self.current_dbfs:.1f} dBFS) | "
            f"Piso Ruido: {self.noise_floor_rms:.4f} | "
            f"Umbral: {self.user_threshold_rms:.4f} | "
            f"SNR: +{self.snr_db:.1f} dB"
        )

        # Update VAD Banner
        if self.is_speech_active:
            dur = time.time() - self.speech_start_time
            self.vad_banner.set_label("🎙️ [ VOZ ACTIVA DETECTADA ]")
            self.vad_banner.get_style_context().remove_class("vad-banner-silence")
            self.vad_banner.get_style_context().add_class("vad-banner-speech")
            self.vad_detail_lbl.set_label(f"Duración: {dur:.2f}s | Pico RMS: {self.peak_speech_rms:.4f}")
        else:
            self.vad_banner.set_label("[ SILENCIO / REPOSO ]")
            self.vad_banner.get_style_context().remove_class("vad-banner-speech")
            self.vad_banner.get_style_context().add_class("vad-banner-silence")
            self.vad_detail_lbl.set_label("Esperando que el nivel supere el umbral...")

        return True

    def _on_destroy(self, widget: Any) -> None:
        self.running = False
        try:
            start_iter = self.log_buffer.get_start_iter()
            end_iter = self.log_buffer.get_end_iter()
            log_text = self.log_buffer.get_text(start_iter, end_iter, True)
            target = "/tmp/opendictate_audio_debug.log"
            with open(target, "w") as f:
                f.write(log_text)
            print(f"Log saved to {target}")
        except Exception as e:
            print(f"Error saving log: {e}")
        Gtk.main_quit()


if __name__ == "__main__":
    app = AudioCalibrationTester()
    app.show_all()
    Gtk.main()

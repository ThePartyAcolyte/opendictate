#!/usr/bin/env python3
"""
Interactive live preview script for the OpenDictate Dual-Mode Bubble.
Simulates real-time transcription and audio levels for manual testing and visual tuning.
"""

import os
import sys
import math
import time

# Auto re-exec in virtual environment if available
venv_python = os.path.expanduser("~/.local/share/opendictate/.venv/bin/python")
if os.path.exists(venv_python) and sys.executable != venv_python and "VIRTUAL_ENV" not in os.environ:
    os.execv(venv_python, [venv_python] + sys.argv)

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from ui.bubble import BubbleWindow
from i18n import get_translator


class BubblePreviewTester:
    def __init__(self):
        self.i18n = get_translator("es")
        self.config = {
            "window_x": -1,
            "window_y": -1,
            "window_width": 460,
            "window_height": 130,
            "bubble_mode": "interactive"
        }

        self.bubble = BubbleWindow(
            config=self.config,
            i18n=self.i18n,
            on_toggle_record_pause=self._on_record_pause,
            on_send=self._on_send,
            on_cancel=self._on_cancel
        )

        self.is_recording = True
        self.is_paused = False
        self.is_interactive = True
        self.tick_count = 0
        self.start_time = time.time()

        # Build floating control toolbar for tester
        self.toolbar_win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.toolbar_win.set_title("OpenDictate - Bubble Tester")
        self.toolbar_win.set_default_size(360, 60)
        self.toolbar_win.set_position(Gtk.WindowPosition.CENTER)
        self.toolbar_win.connect("destroy", Gtk.main_quit)

        t_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        t_box.set_margin_top(10)
        t_box.set_margin_bottom(10)
        t_box.set_margin_left(14)
        t_box.set_margin_right(14)
        self.toolbar_win.add(t_box)

        self.btn_toggle_mode = Gtk.Button(label="Modo: Interactivo")
        self.btn_toggle_mode.connect("clicked", self._toggle_interactive_mode)
        t_box.pack_start(self.btn_toggle_mode, True, True, 0)

        self.btn_sim_process = Gtk.Button(label="Simular Transcripción")
        self.btn_sim_process.connect("clicked", self._simulate_processing)
        t_box.pack_start(self.btn_sim_process, True, True, 0)

        self.toolbar_win.show_all()

        # Launch bubble in recording state
        self.bubble.set_interactive_mode(True)
        self.bubble.show_recording_state(start_time=self.start_time)
        self.bubble.set_live_text("Dictando notas importantes para la reunión de arquitectura del sistema...")

        # Timer for simulated audio level pulse and timer update
        GLib.timeout_add(80, self._simulation_tick)

    def _simulation_tick(self) -> bool:
        if self.is_recording and not self.is_paused:
            self.tick_count += 1
            # Generate organic sine-wave audio level between 0.15 and 0.85
            sim_lvl = 0.5 + 0.35 * math.sin(self.tick_count * 0.25) * math.cos(self.tick_count * 0.1)
            self.bubble.update_audio_level(sim_lvl)
        return True

    def _toggle_interactive_mode(self, btn: Gtk.Button) -> None:
        self.is_interactive = not self.is_interactive
        self.bubble.set_interactive_mode(self.is_interactive)
        mode_str = "Interactivo" if self.is_interactive else "Solo Texto (OSD)"
        btn.set_label(f"Modo: {mode_str}")

    def _simulate_processing(self, btn: Gtk.Button) -> None:
        self.bubble.show_processing_state("Limpiando con IA...")
        GLib.timeout_add(2500, lambda: (
            self.bubble.show_recording_state(start_time=time.time()),
            self.bubble.set_live_text("Texto limpio: 'Este es el resultado final optimizado por Gemini AI.'")
        ))

    def _on_record_pause(self) -> None:
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.bubble.show_paused_state(start_time=self.start_time, pause_start_time=time.time())
        else:
            self.bubble.show_recording_state(start_time=self.start_time)

    def _on_send(self) -> None:
        print("[Tester] Simular Enviar")

    def _on_cancel(self) -> None:
        print("[Tester] Simular Cancelar")


def main():
    BubblePreviewTester()
    Gtk.main()


if __name__ == "__main__":
    main()

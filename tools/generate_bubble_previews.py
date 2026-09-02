#!/usr/bin/env python3
"""
Offscreen PNG generator for OpenDictate Bubble previews.
Generates img/bubble_preview_text.png and img/bubble_preview_interactive.png.
"""

import os
import sys
import cairo

# Auto re-exec in virtual environment if available
venv_python = os.path.expanduser("~/.local/share/opendictate/.venv/bin/python")
if os.path.exists(venv_python) and sys.executable != venv_python and "VIRTUAL_ENV" not in os.environ:
    os.execv(venv_python, [venv_python] + sys.argv)

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from ui.bubble import BubbleWindow
from i18n import get_translator


def generate_preview(is_interactive: bool, output_path: str, is_compact: bool = False):
    config = {
        "window_x": 0,
        "window_y": 0,
        "window_width": 340,
        "window_height": 42 if is_compact else (110 if is_interactive else 60),
        "bubble_mode": "interactive" if (is_interactive or is_compact) else "text",
        "bubble_text_collapsed": is_compact
    }
    i18n = get_translator("es")
    bubble = BubbleWindow(config=config, i18n=i18n)
    bubble.set_interactive_mode(is_interactive or is_compact)
    bubble.show_recording_state()
    bubble.set_live_text("Dictando notas de la reunión de arquitectura del sistema...")
    bubble.waveform.add_level(0.75)

    bubble.window.show_all()
    if not is_interactive and not is_compact:
        bubble.header_box.hide()
    if is_compact:
        bubble.text_view_scroll.hide()
        bubble.icon_toggle.set_from_icon_name("pan-down-symbolic", Gtk.IconSize.BUTTON)

    # Process events to layout
    for _ in range(40):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)

    if is_compact:
        alloc = bubble.header_box.get_allocation()
        w = max(alloc.width + 20, 320)
        h = 42

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(surface)

        # Draw dark capsule pill background
        import math
        radius = 18.0
        cr.save()
        cr.new_sub_path()
        cr.arc(w - radius, radius, radius, -math.pi / 2, 0)
        cr.arc(w - radius, h - radius, radius, 0, math.pi / 2)
        cr.arc(radius, h - radius, radius, math.pi / 2, math.pi)
        cr.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.set_source_rgba(0.08, 0.08, 0.08, 0.95)
        cr.fill_preserve()
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.15)
        cr.set_line_width(1.0)
        cr.stroke()
        cr.restore()

        # Draw header controls on top
        cr.save()
        cr.translate(10, 4)
        bubble.header_box.draw(cr)
        cr.restore()
    else:
        alloc = bubble.window.get_allocation()
        w = max(alloc.width, 320)
        h = max(alloc.height, 95 if is_interactive else 50)

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(surface)
        bubble.window.draw(cr)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    surface.write_to_png(output_path)
    print(f"✅ Generated preview: {output_path} ({w}x{h}, {os.path.getsize(output_path)} bytes)")
    bubble.window.destroy()


def main():
    img_dir = os.path.join(root_dir, "img")
    generate_preview(is_interactive=False, output_path=os.path.join(img_dir, "bubble_preview_text.png"))
    generate_preview(is_interactive=True, output_path=os.path.join(img_dir, "bubble_preview_interactive.png"), is_compact=False)
    generate_preview(is_interactive=True, output_path=os.path.join(img_dir, "bubble_preview_compact.png"), is_compact=True)


if __name__ == "__main__":
    main()

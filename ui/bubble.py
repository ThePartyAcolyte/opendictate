"""
Floating GTK OSD text bubble window for OpenDictate.

Displays live transcript preview, audio level bar, timer, and quick action buttons.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from typing import Dict, Any, Callable, Optional


class BubbleWindow:
    """GTK TopLevel transparent overlay bubble window."""

    def __init__(
        self,
        config: Dict[str, Any],
        i18n: Any,
        on_cancel: Callable[[], None],
        on_copy: Callable[[], None],
        on_finish: Callable[[], None]
    ) -> None:
        """Initialize GTK window components, CSS styles, and event signals."""
        self.config = config
        self.i18n = i18n
        self.on_cancel = on_cancel
        self.on_copy = on_copy
        self.on_finish = on_finish

        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_decorated(False)
        self.window.set_keep_above(True)
        self.window.set_accept_focus(False)
        self.window.set_type_hint(Gdk.WindowTypeHint.UTILITY)

        # Restore saved window geometry
        saved_x = self.config.get("window_x", -1)
        saved_y = self.config.get("window_y", -1)
        saved_w = self.config.get("window_width", -1)
        saved_h = self.config.get("window_height", -1)

        if saved_x != -1 and saved_y != -1:
            self.window.move(saved_x, saved_y)
        else:
            self.window.set_position(Gtk.WindowPosition.CENTER)

        if saved_w != -1 and saved_h != -1:
            self.window.resize(saved_w, saved_h)

        self.window.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.window.connect("button-press-event", self._on_button_press)

        screen = self.window.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.window.set_visual(visual)
        self.window.set_app_paintable(True)

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.box.set_name("bubble-window")

        self.status_icon = Gtk.Label(label="⚪")
        self.status_icon.set_name("status-icon")
        self.status_icon.set_halign(Gtk.Align.CENTER)

        self.time_label = Gtk.Label(label="00:00")
        self.time_label.set_name("time-label")
        self.time_label.set_halign(Gtk.Align.CENTER)

        self.level_bar = Gtk.LevelBar()
        self.level_bar.set_name("level-bar")
        self.level_bar.set_min_value(0.0)
        self.level_bar.set_max_value(1.0)
        self.level_bar.set_size_request(150, 8)

        self.text_buffer = Gtk.TextBuffer()
        self.text_view = Gtk.TextView(buffer=self.text_buffer)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_name("preview-text")

        self.text_view_scroll = Gtk.ScrolledWindow()
        self.text_view_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.text_view_scroll.set_min_content_height(100)
        self.text_view_scroll.set_min_content_width(300)
        self.text_view_scroll.add(self.text_view)

        self.button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.button_box.set_halign(Gtk.Align.CENTER)

        self.btn_close = Gtk.Button(label="❌")
        self.btn_close.set_tooltip_text(self.i18n.t("close"))
        self.btn_close.connect("clicked", lambda w: self.on_cancel())

        self.btn_copy = Gtk.Button(label="📋")
        self.btn_copy.set_tooltip_text(self.i18n.t("copy_clipboard"))
        self.btn_copy.connect("clicked", lambda w: self.on_copy())

        self.btn_insert = Gtk.Button(label="📝")
        self.btn_insert.set_tooltip_text(self.i18n.t("insert_text"))
        self.btn_insert.connect("clicked", lambda w: self.on_finish())

        self.button_box.pack_start(self.btn_close, False, False, 0)
        self.button_box.pack_start(self.btn_copy, False, False, 0)
        self.button_box.pack_start(self.btn_insert, False, False, 0)

        self.box.pack_start(self.status_icon, False, False, 0)
        self.box.pack_start(self.text_view_scroll, True, True, 0)
        self.box.pack_start(self.time_label, False, False, 0)
        self.box.pack_start(self.level_bar, False, False, 0)
        self.box.pack_start(self.button_box, False, False, 0)

        self.window.add(self.box)

        css_provider = Gtk.CssProvider()
        css = b"""
        #bubble-window {
            background-color: rgba(30, 30, 30, 0.95);
            padding: 20px 30px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
        }
        #status-icon { font-size: 36px; }
        #time-label { color: #aaaaaa; font-size: 14px; }
        #preview-text, textview text, textview {
            background-color: transparent;
            color: white;
            font-size: 16px;
        }
        scrolledwindow { background-color: transparent; }
        #level-bar block.filled { background-color: #4CAF50; border-radius: 2px; }
        #level-bar.transcribing block.filled { background-color: #2196F3; }
        #level-bar.cleaning block.filled { background-color: #9C27B0; }
        button {
            padding: 8px 12px;
            border-radius: 6px;
            background-color: rgba(255,255,255,0.1);
            color: white;
            border: none;
        }
        button:hover { background-color: rgba(255,255,255,0.2); }
        scrollbar, scrollbar trough, scrollbar slider {
            min-width: 0px; min-height: 0px;
            background-color: transparent; background: transparent; border: none;
        }
        """
        css_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.window.connect("draw", self._on_draw)

    def _on_button_press(self, widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        """Handle window drag and resize interactions."""
        if event.button == 1:
            self.window.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
            return False
        elif event.button == 3:
            self.window.begin_resize_drag(Gdk.WindowEdge.SOUTH_EAST, event.button, int(event.x_root), int(event.y_root), event.time)
            return False
        return False

    def _on_draw(self, widget: Gtk.Widget, cr: Any) -> bool:
        """Clear window background for cairo alpha transparency."""
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)
        cr.paint()
        return False

    def show_recording_state(self) -> None:
        """Configure layout for RECORDING or PAUSED state."""
        self.window.show_all()
        self.status_icon.show()
        self.time_label.show()
        self.level_bar.show()
        self.text_view_scroll.hide()
        self.button_box.show_all()
        self.btn_copy.hide()
        self.btn_insert.hide()
        self.btn_close.show()

    def show_processing_state(self) -> None:
        """Configure layout for TRANSCRIBING or CLEANING processing state with cancel button."""
        self.window.show_all()
        self.status_icon.show()
        self.time_label.show()
        self.level_bar.show()
        self.text_view_scroll.hide()
        self.button_box.show_all()
        self.btn_copy.hide()
        self.btn_insert.hide()
        self.btn_close.show()

    def show_preview_state(self, text: str) -> None:
        """Configure window layout for PREVIEW state showing text buffer and action buttons."""
        self.window.show_all()
        self.status_icon.hide()
        self.time_label.hide()
        self.level_bar.hide()

        self.text_buffer.set_text(text)
        self.text_view_scroll.show_all()
        self.button_box.show_all()
        self.btn_close.show()
        self.btn_copy.show()
        self.btn_insert.show()

    def set_live_text(self, text: str) -> None:
        """Update preview text buffer and auto-scroll to end."""
        self.text_buffer.set_text(text)
        end_iter = self.text_buffer.get_end_iter()
        mark = self.text_buffer.create_mark(None, end_iter, False)
        self.text_view.scroll_mark_onscreen(mark)

    def hide(self) -> None:
        """Hide the GTK bubble window."""
        self.window.hide()

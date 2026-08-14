"""
Floating GTK OSD text bubble window for OpenDictate.

Displays live transcript preview with Cairo rendering, typing animation, and minimalist design.
"""

import math
import cairo
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from typing import Dict, Any, List, Optional


class BubbleWindow:
    """GTK TopLevel transparent overlay bubble window with Cairo background rendering."""

    def __init__(
        self,
        config: Dict[str, Any],
        i18n: Any
    ) -> None:
        """Initialize GTK window components, CSS styles, and event signals."""
        self.config = config
        self.i18n = i18n

        # Animation & Streaming State
        self.displayed_text: str = ""
        self.target_text: str = ""
        self.queue_words: List[str] = []
        self.cursor_visible: bool = True
        self.cursor_active: bool = False
        self.anim_timer_id: Optional[int] = None
        self.blink_timer_id: Optional[int] = None

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

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.box.set_name("bubble-window")

        self.text_buffer = Gtk.TextBuffer()
        self.cursor_tag = self.text_buffer.create_tag("cursor-tag", foreground_rgba=Gdk.RGBA(1.0, 1.0, 1.0, 1.0))
        self.text_view = Gtk.TextView(buffer=self.text_buffer)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_name("preview-text")
        self.text_view.set_left_margin(12)
        self.text_view.set_right_margin(12)
        self.text_view.set_top_margin(10)
        self.text_view.set_bottom_margin(10)

        self.text_view_scroll = Gtk.ScrolledWindow()
        self.text_view_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.text_view_scroll.set_min_content_height(80)
        self.text_view_scroll.set_max_content_height(320)
        self.text_view_scroll.set_propagate_natural_height(True)
        self.text_view_scroll.set_min_content_width(350)
        self.text_view_scroll.add(self.text_view)

        self.level_bar = Gtk.LevelBar()
        self.level_bar.set_name("level-bar")
        self.level_bar.set_min_value(0.0)
        self.level_bar.set_max_value(1.0)
        self.level_bar.set_size_request(-1, 2)
        self.level_bar.set_margin_top(5)
        self.level_bar.set_margin_bottom(6)
        self.level_bar.set_margin_left(12)
        self.level_bar.set_margin_right(12)

        self.box.pack_start(self.text_view_scroll, True, True, 0)
        self.box.pack_start(self.level_bar, False, False, 0)

        self.window.add(self.box)

        css_provider = Gtk.CssProvider()
        css = b"""
        #bubble-window {
            background-color: transparent;
            padding: 5px;
        }
        #preview-text, textview text, textview {
            background-color: transparent;
            color: rgba(255, 255, 255, 0.95);
            font-size: 18px;
            font-family: sans-serif;
        }
        scrolledwindow { background-color: transparent; }
        
        #level-bar { 
            background-color: transparent;
            min-height: 2px;
        }
        #level-bar trough {
            background-color: transparent;
        }
        #level-bar block.filled { 
            background-color: rgba(100, 200, 255, 0.85); 
            border-radius: 2px; 
            box-shadow: 0 0 8px 1px rgba(100, 200, 255, 0.6);
        }
        #level-bar.transcribing block.filled { 
            background-color: rgba(156, 39, 176, 0.85);
            box-shadow: 0 0 8px 1px rgba(156, 39, 176, 0.6);
        }
        
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
        """Draw rounded dark background using Cairo to prevent transparency issues."""
        alloc = widget.get_allocation()
        w = float(alloc.width)
        h = float(alloc.height)
        radius = 14.0

        # Clear background completely
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()

        # Draw rounded box
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.new_sub_path()
        cr.arc(w - radius, radius, radius, -math.pi / 2, 0)
        cr.arc(w - radius, h - radius, radius, 0, math.pi / 2)
        cr.arc(radius, h - radius, radius, math.pi / 2, math.pi)
        cr.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
        cr.close_path()

        # Fill background with dark 92% opaque color
        cr.set_source_rgba(0.08, 0.08, 0.08, 0.92)
        cr.fill_preserve()

        # Draw subtle top border/glow
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.08)
        cr.set_line_width(1.0)
        cr.stroke()

        return False

    def _start_timers(self) -> None:
        """Start cursor blinking and word streaming animation timers."""
        self.cursor_active = True
        self.cursor_visible = True
        self.cursor_tag.set_property("foreground-rgba", Gdk.RGBA(1.0, 1.0, 1.0, 1.0))
        if not self.blink_timer_id:
            self.blink_timer_id = GLib.timeout_add(450, self._blink_cursor)
        if not self.anim_timer_id:
            self.anim_timer_id = GLib.timeout_add(70, self._animate_step)

    def _stop_timers(self) -> None:
        """Stop animation timers and remove blinking cursor."""
        self.cursor_active = False
        if self.blink_timer_id:
            GLib.source_remove(self.blink_timer_id)
            self.blink_timer_id = None
        if self.anim_timer_id:
            GLib.source_remove(self.anim_timer_id)
            self.anim_timer_id = None

    def _blink_cursor(self) -> bool:
        """Toggle cursor alpha transparency without altering buffer length."""
        if not self.cursor_active:
            return False
        self.cursor_visible = not self.cursor_visible
        alpha = 1.0 if self.cursor_visible else 0.0
        self.cursor_tag.set_property("foreground-rgba", Gdk.RGBA(1.0, 1.0, 1.0, alpha))
        return True

    def _animate_step(self) -> bool:
        """Dequeue words and smoothly append to displayed text buffer."""
        if not self.cursor_active:
            return False

        if self.queue_words:
            next_word = self.queue_words.pop(0)
            if self.displayed_text and not self.displayed_text.endswith(" ") and not next_word.startswith(" "):
                self.displayed_text += " " + next_word
            else:
                self.displayed_text += next_word
            self._update_text_buffer()
        elif self.displayed_text != self.target_text and self.target_text.startswith(self.displayed_text):
            remaining = self.target_text[len(self.displayed_text):]
            words = [w for w in remaining.split(" ") if w]
            if words:
                word = words[0]
                if self.displayed_text and not self.displayed_text.endswith(" "):
                    self.displayed_text += " " + word
                else:
                    self.displayed_text += word
                self._update_text_buffer()

        return True

    def _update_text_buffer(self) -> None:
        """Update GTK text buffer with current text + permanent cursor character, applying transparency tag."""
        if self.cursor_active:
            text_to_show = self.displayed_text + " ▌"
            self.text_buffer.set_text(text_to_show)
            start_iter = self.text_buffer.get_iter_at_offset(len(text_to_show) - 2)
            end_iter = self.text_buffer.get_end_iter()
            self.text_buffer.apply_tag(self.cursor_tag, start_iter, end_iter)
        else:
            self.text_buffer.set_text(self.displayed_text)

        end_iter = self.text_buffer.get_end_iter()
        mark = self.text_buffer.create_mark(None, end_iter, False)
        self.text_view.scroll_mark_onscreen(mark)

    def show_recording_state(self) -> None:
        """Configure layout for RECORDING or PAUSED state."""
        self.displayed_text = ""
        self.target_text = ""
        self.queue_words.clear()
        self.text_buffer.set_text("")
        self._start_timers()
        self.level_bar.get_style_context().remove_class("transcribing")
        self.level_bar.show()
        self.window.show_all()

    def show_processing_state(self) -> None:
        """Configure layout for TRANSCRIBING processing state."""
        self.level_bar.get_style_context().add_class("transcribing")
        self.level_bar.show()
        self.window.show_all()

    def show_preview_state(self, text: str) -> None:
        """Configure window layout for PREVIEW state showing final text buffer."""
        self._stop_timers()
        self.displayed_text = text
        self.target_text = text
        self.queue_words.clear()
        self.text_buffer.set_text(text)
        self.level_bar.hide()
        self.window.show_all()

    def set_live_text(self, text: str) -> None:
        """Update target preview text and queue new words for smooth streaming animation."""
        if text == self.target_text:
            return

        if text.startswith(self.displayed_text):
            new_part = text[len(self.displayed_text):]
            if self.target_text and text.startswith(self.target_text):
                new_part = text[len(self.target_text):]
            
            new_words = [w for w in new_part.split(" ") if w]
            self.queue_words.extend(new_words)
        else:
            # Re-sync if text was modified upstream
            self.displayed_text = text
            self.queue_words.clear()
            self._update_text_buffer()

        self.target_text = text
        self._start_timers()

    def hide(self) -> None:
        """Hide the GTK bubble window."""
        self._stop_timers()
        self.displayed_text = ""
        self.target_text = ""
        self.queue_words.clear()
        self.text_buffer.set_text("")
        self.window.hide()

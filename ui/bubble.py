"""
Floating GTK OSD text bubble and interactive control capsule for OpenDictate.

Supports Dual-Mode operation:
1. Minimalist Text OSD Mode (for GNOME extension users / clean distraction-free preview).
2. Interactive Widget Mode (for non-GNOME environments / standalone usage with header controls).
"""

import math
import time
import cairo
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from typing import Dict, Any, List, Optional, Callable


class WaveformArea(Gtk.DrawingArea):
    """Custom Cairo drawing area that renders real-time audio levels or an indeterminate pulse."""

    def __init__(self, bar_count: int = 24) -> None:
        super().__init__()
        self.bar_count = bar_count
        self._levels: List[float] = [0.0] * self.bar_count
        self._is_indeterminate: bool = False
        self._pulse_pos: float = 0.0
        self._pulse_dir: int = 1
        self.set_size_request(80, 20)
        self.connect("draw", self._on_draw)

    def set_indeterminate(self, enable: bool) -> None:
        if self._is_indeterminate != enable:
            self._is_indeterminate = enable
            self._pulse_pos = 0.0
            self._pulse_dir = 1
            self.queue_draw()

    def update_pulse(self) -> None:
        if not self._is_indeterminate:
            return
        self._pulse_pos += 0.05 * self._pulse_dir
        if self._pulse_pos >= 1.0:
            self._pulse_pos = 1.0
            self._pulse_dir = -1
        elif self._pulse_pos <= 0.0:
            self._pulse_pos = 0.0
            self._pulse_dir = 1
        self.queue_draw()

    def add_level(self, level: float) -> None:
        self._levels.pop(0)
        self._levels.append(max(0.0, min(1.0, level)))
        self.queue_draw()

    def reset_levels(self) -> None:
        self._levels = [0.0] * self.bar_count
        self._is_indeterminate = False
        self.queue_draw()

    def _on_draw(self, widget: Gtk.Widget, cr: Any) -> bool:
        alloc = widget.get_allocation()
        w = float(alloc.width)
        h = float(alloc.height)

        if self._is_indeterminate:
            pulse_width = w * 0.4
            start_x = (w - pulse_width) * self._pulse_pos
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.2)
            cr.set_line_width(3.0)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.move_to(0, h / 2)
            cr.line_to(w, h / 2)
            cr.stroke()

            cr.set_source_rgba(0.2, 0.6, 1.0, 0.95)
            cr.set_line_width(3.5)
            cr.move_to(start_x, h / 2)
            cr.line_to(start_x + pulse_width, h / 2)
            cr.stroke()
            return False

        cr.set_source_rgba(1.0, 1.0, 1.0, 0.75)
        cr.set_line_width(2.0)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)

        step = w / max(1, (self.bar_count - 1))
        for i in range(self.bar_count):
            val = self._levels[i] * (h / 2.2)
            x = i * step
            y1 = (h / 2.0) - val
            y2 = (h / 2.0) + val
            if val < 0.5:
                y1 = (h / 2.0) - 0.5
                y2 = (h / 2.0) + 0.5
            cr.move_to(x, y1)
            cr.line_to(x, y2)
        cr.stroke()
        return False


class BubbleWindow:
    """GTK TopLevel transparent overlay bubble window supporting dual-mode interaction."""

    def __init__(
        self,
        config: Dict[str, Any],
        i18n: Any,
        on_toggle_record_pause: Optional[Callable[[], None]] = None,
        on_send: Optional[Callable[[], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None
    ) -> None:
        self.config = config
        self.i18n = i18n
        self.on_toggle_record_pause = on_toggle_record_pause
        self.on_send = on_send
        self.on_cancel = on_cancel

        # Interactive Mode & Text Collapse State
        self.interactive_mode: bool = False
        self.text_collapsed: bool = bool(self.config.get("bubble_text_collapsed", False)) if isinstance(self.config, dict) else False
        self.state: str = "IDLE"
        self.start_time: float = 0.0
        self.total_paused_time: float = 0.0
        self.pause_start_time: Optional[float] = None

        # Animation & Streaming State
        self.displayed_text: str = ""
        self.target_text: str = ""
        self.queue_words: List[str] = []
        self.cursor_visible: bool = True
        self.cursor_active: bool = False
        self.anim_timer_id: Optional[int] = None
        self.blink_timer_id: Optional[int] = None
        self.clock_timer_id: Optional[int] = None
        self.pulse_timer_id: Optional[int] = None

        # TopLevel Window Configuration
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_decorated(False)
        self.window.set_keep_above(True)
        self.window.set_accept_focus(False)  # Crucial: Prevent stealing focus on button click
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

        # Main Vertical Container
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.box.set_name("bubble-window")

        # ---------------------------------------------------------
        # Interactive Header Bar
        # ---------------------------------------------------------
        self.header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.header_box.set_name("bubble-header")
        self.header_box.set_margin_left(6)
        self.header_box.set_margin_right(6)
        self.header_box.set_margin_top(4)
        self.header_box.set_margin_bottom(2)

        # Record / Pause Action Button
        self.btn_record_pause = Gtk.Button()
        self.btn_record_pause.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_record_pause.set_name("bubble-btn-record")
        self.icon_record_pause = Gtk.Image.new_from_icon_name("audio-input-microphone-symbolic", Gtk.IconSize.BUTTON)
        self.btn_record_pause.set_image(self.icon_record_pause)
        self.btn_record_pause.set_tooltip_text(self.i18n.t("tooltip_record"))
        self.btn_record_pause.connect("clicked", self._on_record_pause_clicked)
        self.header_box.pack_start(self.btn_record_pause, False, False, 0)

        # Waveform Visualizer
        self.waveform = WaveformArea(bar_count=20)
        self.waveform.set_valign(Gtk.Align.CENTER)
        self.header_box.pack_start(self.waveform, True, True, 4)

        # Status / Timer Label
        self.lbl_status = Gtk.Label(label="00:00")
        self.lbl_status.set_name("bubble-timer-label")
        self.lbl_status.set_valign(Gtk.Align.CENTER)
        self.header_box.pack_start(self.lbl_status, False, False, 4)

        # Send Action Button
        self.btn_send = Gtk.Button()
        self.btn_send.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_send.set_name("bubble-btn-send")
        self.icon_send = Gtk.Image.new_from_icon_name("mail-send-symbolic", Gtk.IconSize.BUTTON)
        self.btn_send.set_image(self.icon_send)
        self.btn_send.set_tooltip_text(self.i18n.t("tooltip_send"))
        self.btn_send.connect("clicked", self._on_send_clicked)
        self.header_box.pack_start(self.btn_send, False, False, 0)

        # Cancel Action Button
        self.btn_cancel = Gtk.Button()
        self.btn_cancel.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_cancel.set_name("bubble-btn-cancel")
        self.icon_cancel = Gtk.Image.new_from_icon_name("process-stop-symbolic", Gtk.IconSize.BUTTON)
        self.btn_cancel.set_image(self.icon_cancel)
        self.btn_cancel.set_tooltip_text(self.i18n.t("tooltip_cancel"))
        self.btn_cancel.connect("clicked", self._on_cancel_clicked)
        self.header_box.pack_start(self.btn_cancel, False, False, 0)

        # Toggle Expand / Collapse Text Box Button
        self.btn_toggle_text = Gtk.Button()
        self.btn_toggle_text.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_toggle_text.set_name("bubble-btn-toggle")
        self.icon_toggle = Gtk.Image.new_from_icon_name("pan-up-symbolic", Gtk.IconSize.BUTTON)
        self.btn_toggle_text.set_image(self.icon_toggle)
        self.btn_toggle_text.set_tooltip_text(self.i18n.t("tooltip_toggle_text"))
        self.btn_toggle_text.connect("clicked", self._on_toggle_text_clicked)
        self.header_box.pack_start(self.btn_toggle_text, False, False, 0)

        self.box.pack_start(self.header_box, False, False, 0)

        # ---------------------------------------------------------
        # Text Preview Area
        # ---------------------------------------------------------
        self.text_buffer = Gtk.TextBuffer()
        self.cursor_tag = self.text_buffer.create_tag("cursor-tag", foreground_rgba=Gdk.RGBA(1.0, 1.0, 1.0, 1.0))
        self.text_view = Gtk.TextView(buffer=self.text_buffer)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_name("preview-text")
        self.text_view.set_left_margin(12)
        self.text_view.set_right_margin(12)
        self.text_view.set_top_margin(8)
        self.text_view.set_bottom_margin(8)

        self.text_view_scroll = Gtk.ScrolledWindow()
        self.text_view_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.text_view_scroll.set_min_content_height(70)
        self.text_view_scroll.set_max_content_height(320)
        self.text_view_scroll.set_propagate_natural_height(True)
        self.text_view_scroll.set_min_content_width(340)
        self.text_view_scroll.add(self.text_view)

        self.box.pack_start(self.text_view_scroll, True, True, 0)
        self.window.add(self.box)

        # Apply CSS
        self._apply_css(screen)
        self.window.connect("draw", self._on_draw)

        # Initial mode setup
        self.set_interactive_mode(False)

    def _apply_css(self, screen: Gdk.Screen) -> None:
        css_provider = Gtk.CssProvider()
        css = b"""
        #bubble-window {
            background-color: transparent;
            padding: 4px;
        }
        #bubble-header {
            background-color: transparent;
        }
        #preview-text, textview text, textview {
            background-color: transparent;
            color: rgba(255, 255, 255, 0.95);
            font-size: 17px;
            font-family: sans-serif;
        }
        scrolledwindow { background-color: transparent; }

        #bubble-timer-label {
            color: #d0d0d0;
            font-size: 12px;
            font-weight: bold;
            font-family: monospace;
        }

        #bubble-btn-record, #bubble-btn-send, #bubble-btn-cancel, #bubble-btn-toggle {
            background-color: rgba(255, 255, 255, 0.07);
            border-radius: 16px;
            padding: 4px 6px;
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.1);
            transition: all 120ms ease;
        }
        #bubble-btn-record:hover, #bubble-btn-send:hover, #bubble-btn-cancel:hover, #bubble-btn-toggle:hover {
            background-color: rgba(255, 255, 255, 0.18);
            border-color: rgba(255, 255, 255, 0.25);
        }
        #bubble-btn-record.recording {
            background-color: rgba(235, 77, 75, 0.35);
            border-color: rgba(235, 77, 75, 0.7);
            color: #ff6b6b;
        }
        #bubble-btn-record.paused {
            background-color: rgba(243, 156, 18, 0.35);
            border-color: rgba(243, 156, 18, 0.7);
            color: #f1c40f;
        }
        #bubble-btn-send {
            color: #2ecc71;
        }
        #bubble-btn-cancel {
            color: #e74c3c;
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

    def set_interactive_mode(self, enabled: bool) -> None:
        """Toggle between interactive header mode and minimalist text-only OSD mode."""
        self.interactive_mode = enabled
        if self.interactive_mode:
            self.header_box.show_all()
        else:
            self.header_box.hide()
            self.text_view_scroll.show()

    def set_text_collapsed(self, collapsed: bool) -> None:
        """Toggle text preview area visibility for compact floating capsule."""
        self.text_collapsed = collapsed
        if isinstance(self.config, dict):
            self.config["bubble_text_collapsed"] = self.text_collapsed
            try:
                from core.config import ConfigManager
                ConfigManager().save_config(self.config)
            except Exception:
                pass
        if self.text_collapsed and self.interactive_mode:
            self.text_view_scroll.hide()
            self.icon_toggle.set_from_icon_name("pan-down-symbolic", Gtk.IconSize.BUTTON)
            self.window.resize(300, 42)
        else:
            self.text_view_scroll.show()
            self.icon_toggle.set_from_icon_name("pan-up-symbolic", Gtk.IconSize.BUTTON)

    def _on_record_pause_clicked(self, widget: Gtk.Button) -> None:
        if self.on_toggle_record_pause:
            self.on_toggle_record_pause()

    def _on_send_clicked(self, widget: Gtk.Button) -> None:
        if self.on_send:
            self.on_send()

    def _on_cancel_clicked(self, widget: Gtk.Button) -> None:
        if self.on_cancel:
            self.on_cancel()

    def _on_toggle_text_clicked(self, widget: Gtk.Button) -> None:
        self.set_text_collapsed(not self.text_collapsed)

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
        """Draw rounded dark translucent background using Cairo."""
        alloc = widget.get_allocation()
        w = float(alloc.width)
        h = float(alloc.height)
        radius = 18.0 if (self.text_collapsed and self.interactive_mode) else 14.0

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

        # Draw subtle border
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.1)
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
        if self.clock_timer_id:
            GLib.source_remove(self.clock_timer_id)
            self.clock_timer_id = None
        if self.pulse_timer_id:
            GLib.source_remove(self.pulse_timer_id)
            self.pulse_timer_id = None

    def _blink_cursor(self) -> bool:
        if not self.cursor_active:
            return False
        self.cursor_visible = not self.cursor_visible
        alpha = 1.0 if self.cursor_visible else 0.0
        self.cursor_tag.set_property("foreground-rgba", Gdk.RGBA(1.0, 1.0, 1.0, alpha))
        return True

    def _animate_step(self) -> bool:
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

    def _update_time_display(self) -> bool:
        if self.state not in ("RECORDING", "PAUSED"):
            return False

        now = time.time()
        if self.state == "RECORDING":
            elapsed = now - self.start_time - self.total_paused_time
        else:
            p_start = self.pause_start_time or now
            elapsed = p_start - self.start_time - self.total_paused_time

        if elapsed < 0:
            elapsed = 0

        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        self.lbl_status.set_text(f"{mins:02d}:{secs:02d}")
        return True

    def show_recording_state(self, start_time: float = 0.0, total_paused_time: float = 0.0) -> None:
        """Configure layout for RECORDING state."""
        if self.config.get("hide_bubble", False):
            return

        self.state = "RECORDING"
        self.start_time = start_time or time.time()
        self.total_paused_time = total_paused_time
        self.pause_start_time = None

        self.displayed_text = ""
        self.target_text = ""
        self.queue_words.clear()
        self.text_buffer.set_text("")
        self._start_timers()

        self.waveform.reset_levels()
        self.icon_record_pause.set_from_icon_name("media-playback-pause-symbolic", Gtk.IconSize.BUTTON)
        self.btn_record_pause.get_style_context().remove_class("paused")
        self.btn_record_pause.get_style_context().add_class("recording")
        self.btn_send.show()
        self.btn_cancel.show()

        self._update_time_display()
        if not self.clock_timer_id:
            self.clock_timer_id = GLib.timeout_add(500, self._update_time_display)

        if self.interactive_mode:
            self.header_box.show_all()
            if self.text_collapsed:
                self.text_view_scroll.hide()
        else:
            self.header_box.hide()
            self.text_view_scroll.show()

        self.window.show_all()

    def show_paused_state(self, start_time: float = 0.0, pause_start_time: float = 0.0, total_paused_time: float = 0.0) -> None:
        """Configure layout for PAUSED state."""
        if self.config.get("hide_bubble", False):
            return

        self.state = "PAUSED"
        self.start_time = start_time or self.start_time
        self.pause_start_time = pause_start_time or time.time()
        self.total_paused_time = total_paused_time

        self.icon_record_pause.set_from_icon_name("media-record-symbolic", Gtk.IconSize.BUTTON)
        self.btn_record_pause.get_style_context().remove_class("recording")
        self.btn_record_pause.get_style_context().add_class("paused")

        self._update_time_display()
        if self.clock_timer_id:
            GLib.source_remove(self.clock_timer_id)
            self.clock_timer_id = None

        self.window.show_all()

    def show_processing_state(self, status_text: str = "") -> None:
        """Configure layout for TRANSCRIBING / CLEANING processing state."""
        if self.config.get("hide_bubble", False):
            return

        self.state = "PROCESSING"
        self.waveform.set_indeterminate(True)
        if not self.pulse_timer_id:
            self.pulse_timer_id = GLib.timeout_add(40, lambda: (self.waveform.update_pulse(), True)[1])

        display_status = status_text or self.i18n.t("processing")
        self.lbl_status.set_text(display_status)
        self.btn_send.hide()
        self.btn_cancel.show()

        if self.interactive_mode:
            self.header_box.show_all()
            self.btn_send.hide()
            if self.text_collapsed:
                self.text_view_scroll.hide()
        else:
            self.header_box.hide()
            self.text_view_scroll.show()

        self.window.show_all()

    def update_audio_level(self, level: float) -> None:
        """Update live waveform level."""
        if self.state == "RECORDING":
            self.waveform.add_level(level)

    def set_live_text(self, text: str) -> None:
        """Update target preview text and queue new words for smooth streaming animation."""
        if self.config.get("hide_bubble", False):
            return

        if text == self.target_text:
            return

        if text.startswith(self.displayed_text):
            new_part = text[len(self.displayed_text):]
            if self.target_text and text.startswith(self.target_text):
                new_part = text[len(self.target_text):]

            new_words = [w for w in new_part.split(" ") if w]
            self.queue_words.extend(new_words)
        else:
            self.displayed_text = text
            self.queue_words.clear()
            self._update_text_buffer()

        self.target_text = text
        self._start_timers()

    def hide(self) -> None:
        """Hide the GTK bubble window and reset state."""
        self._stop_timers()
        self.state = "IDLE"
        self.displayed_text = ""
        self.target_text = ""
        self.queue_words.clear()
        self.text_buffer.set_text("")
        self.waveform.reset_levels()
        self.window.hide()


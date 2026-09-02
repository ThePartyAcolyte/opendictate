"""
System Tray AppIndicator and Gtk Menu manager for OpenDictate.
Dynamic fallback: Uses Gtk.StatusIcon on X11 for left-click support,
and AyatanaAppIndicator3 on Wayland to prevent coordinate rendering bugs.
"""

import logging
import os
from typing import Dict, Any, Callable, Optional
import warnings

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

try:
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
    HAS_APPINDICATOR = True
except (ValueError, ImportError):
    HAS_APPINDICATOR = False

warnings.filterwarnings("ignore", category=DeprecationWarning)

class TrayManager:
    """Manages system tray indicator (AyatanaAppIndicator / Gtk.StatusIcon) and popup menu."""

    def __init__(
        self,
        config: Dict[str, Any],
        i18n: Any,
        on_toggle_record_pause: Callable[[], None],
        on_toggle_auto_send: Callable[[bool], None],
        on_toggle_ai: Callable[[bool], None],
        on_open_config: Callable[[], None],
        on_quit: Callable[[], None],
        show_notification: Callable[[str, str], None]
    ) -> None:
        """Initialize the tray manager with callbacks and configuration.

        Args:
            config: Application configuration dictionary.
            i18n: Translator instance for localized labels.
            on_toggle_record_pause: Callback for primary record/pause action.
            on_toggle_auto_send: Callback for toggling auto-send on paste.
            on_toggle_ai: Callback for toggling AI cleanup.
            on_open_config: Callback for presenting settings window.
            on_quit: Callback for quitting application.
            show_notification: Callback to display system notifications.
        """
        self.config = config
        self.i18n = i18n
        self.on_toggle_record_pause = on_toggle_record_pause
        self.on_toggle_auto_send = on_toggle_auto_send
        self.on_toggle_ai = on_toggle_ai
        self.on_open_config = on_open_config
        self.on_quit = on_quit
        self.show_notification = show_notification

        self.indicator = None
        self.record_menu_item = None
        self.auto_send_check = None
        self.ai_check = None
        self._updating_toggles = False
        
        # Decide backend based on display server
        self.is_wayland = os.environ.get('WAYLAND_DISPLAY') is not None
        self.use_appindicator = self.is_wayland and HAS_APPINDICATOR
        
        self.build_menu()

    def build_menu(self) -> None:
        """Construct or refresh the GTK system tray menu items and bindings."""
        is_omarchy = os.path.exists(os.path.expanduser("~/.config/omarchy/plugins/com.kirulab.opendictate"))
        indicator_mode = self.config.get("indicator_mode", "auto")

        if is_omarchy or indicator_mode in ("omarchy", "gnome_ext") or not self.config.get("use_appindicator", False):
            should_show = False
        else:
            should_show = self.config.get("initial_setup_completed", False)

        if not should_show:
            if self.indicator:
                if self.use_appindicator:
                    try:
                        self.indicator.set_status(AppIndicator.IndicatorStatus.PASSIVE)
                    except Exception: pass
                else:
                    self.indicator.set_visible(False)
                self.indicator = None
            return

        if self.indicator is None:
            if self.use_appindicator:
                self.indicator = AppIndicator.Indicator.new(
                    "opendictate-daemon",
                    "audio-input-microphone",
                    AppIndicator.IndicatorCategory.APPLICATION_STATUS
                )
            else:
                self.indicator = Gtk.StatusIcon()
                self.indicator.set_from_icon_name("audio-input-microphone")
                self.indicator.set_title("OpenDictate")
                self.indicator.connect("activate", self._on_activate)
                self.indicator.connect("popup-menu", self._on_popup_menu)
                self.indicator.set_visible(True)

        self.menu = Gtk.Menu()

        self.record_menu_item = Gtk.MenuItem(label=f"● {self.i18n.t('record') if hasattr(self.i18n, 't') else 'Grabar'}")
        self.record_menu_item.connect('activate', lambda w: self.on_toggle_record_pause())
        self.menu.append(self.record_menu_item)
        self.menu.append(Gtk.SeparatorMenuItem())

        self.auto_send_check = Gtk.CheckMenuItem(label=self.i18n.t("auto_send"))
        self.auto_send_check.set_active(self.config.get("auto_send", False))
        self.auto_send_check.connect("toggled", self._on_auto_send_toggled)
        self.menu.append(self.auto_send_check)

        self.ai_check = Gtk.CheckMenuItem(label=self.i18n.t("ai_cleanup"))
        self.ai_check.set_active(self.config.get("ai_enabled", False))
        self.ai_check.connect("toggled", self._on_ai_toggled)
        self.menu.append(self.ai_check)

        self.menu.append(Gtk.SeparatorMenuItem())

        item_config = Gtk.MenuItem(label=f"⚙️ {self.i18n.t('settings')}")
        item_config.connect('activate', lambda w: self.on_open_config())
        self.menu.append(item_config)

        self.menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label=f"✖ {self.i18n.t('quit')}")
        item_quit.connect('activate', lambda w: self.on_quit())
        self.menu.append(item_quit)

        self.menu.show_all()
        
        if self.use_appindicator:
            self.indicator.set_menu(self.menu)
            self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            try:
                self.indicator.set_secondary_activate_target(self.record_menu_item)
            except Exception: pass

    def _on_activate(self, icon: Gtk.StatusIcon) -> None:
        """Handle left-click on Gtk.StatusIcon (X11).

        Args:
            icon: Gtk.StatusIcon emitting the signal.
        """
        self.on_toggle_record_pause()

    def _on_popup_menu(self, icon: Gtk.StatusIcon, button: int, activate_time: int) -> None:
        """Handle right-click context menu popup on Gtk.StatusIcon (X11).

        Args:
            icon: Gtk.StatusIcon emitting the signal.
            button: Mouse button identifier.
            activate_time: Event timestamp.
        """
        if self.menu:
            self.menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, activate_time)

    def _on_auto_send_toggled(self, widget: Gtk.CheckMenuItem) -> None:
        """Handle auto-send menu checkbox toggle event.

        Args:
            widget: CheckMenuItem being toggled.
        """
        if not self._updating_toggles:
            self.on_toggle_auto_send(widget.get_active())

    def _on_ai_toggled(self, widget: Gtk.CheckMenuItem) -> None:
        """Handle AI cleanup menu checkbox toggle event.

        Args:
            widget: CheckMenuItem being toggled.
        """
        if not self._updating_toggles:
            self.on_toggle_ai(widget.get_active())

    def update_toggles(self, auto_send: bool, ai_enabled: bool) -> None:
        """Synchronize tray checkbox states with application configuration.

        Args:
            auto_send: Active auto-send state.
            ai_enabled: Active AI cleanup state.
        """
        self._updating_toggles = True
        if self.auto_send_check and self.auto_send_check.get_active() != auto_send:
            self.auto_send_check.set_active(auto_send)
        if self.ai_check and self.ai_check.get_active() != ai_enabled:
            self.ai_check.set_active(ai_enabled)
        self._updating_toggles = False

    def set_daemon_state(self, state: str) -> None:
        """Update tray icon and menu action label according to daemon state machine.

        Args:
            state: Current daemon state (e.g. 'IDLE', 'RECORDING', 'PAUSED', 'TRANSCRIBING').
        """
        if not self.indicator:
            return

        icon_name = "audio-input-microphone"
        action_label = f"● {self.i18n.t('record') if hasattr(self.i18n, 't') else 'Grabar'}"

        if state == "RECORDING":
            icon_name = "media-record"
            action_label = f"💬 {self.i18n.t('bubble_visible')}"
        elif state == "PAUSED":
            icon_name = "media-playback-pause"
            action_label = f"💬 {self.i18n.t('bubble_visible')}"
        elif state in ("TRANSCRIBING", "CLEANING", "PROCESSING", "LOADING"):
            icon_name = "process-working"
            action_label = f"⏳ {self.i18n.t('processing')}"

        if self.use_appindicator:
            try:
                self.indicator.set_icon_full(icon_name, "OpenDictate")
            except Exception:
                try:
                    self.indicator.set_icon(icon_name)
                except Exception: pass
        else:
            try:
                self.indicator.set_from_icon_name(icon_name)
            except Exception: pass

        if self.record_menu_item:
            self.record_menu_item.set_label(action_label)

    def set_mic_health(self, health: str) -> None:
        """Update tray indicator state based on microphone saturation/health.

        Args:
            health: 'HEALTHY' or 'CLIPPED'.
        """
        if not self.indicator:
            return

        if health == "CLIPPED":
            if self.use_appindicator:
                try:
                    self.indicator.set_icon_full("audio-volume-high", "OpenDictate (Mic Saturated)")
                except Exception:
                    pass
            elif hasattr(self.indicator, "set_tooltip_text"):
                try:
                    self.indicator.set_tooltip_text("OpenDictate - Micrófono saturado")
                except Exception:
                    pass


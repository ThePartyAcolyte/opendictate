"""
System Tray AppIndicator and Gtk Menu manager for OpenDictate.

Renders status indicator icon, model selection sub-menu, and quick action toggles.
"""

import os
import shutil
import subprocess
import logging
from typing import Dict, Any, Callable, Optional

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

try:
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
    HAS_INDICATOR = True
except (ValueError, ImportError):
    HAS_INDICATOR = False


class TrayManager:
    """Manages system tray AppIndicator icon and context menu."""

    def __init__(
        self,
        config: Dict[str, Any],
        i18n: Any,
        on_model_change: Callable[[str], None],
        on_toggle_auto_send: Callable[[bool], None],
        on_toggle_ai: Callable[[bool], None],
        on_open_config: Callable[[], None],
        on_quit: Callable[[], None],
        show_notification: Callable[[str, str], None]
    ) -> None:
        self.config = config
        self.i18n = i18n
        self.on_model_change = on_model_change
        self.on_toggle_auto_send = on_toggle_auto_send
        self.on_toggle_ai = on_toggle_ai
        self.on_open_config = on_open_config
        self.on_quit = on_quit
        self.show_notification = show_notification

        self.indicator = None
        self.status_menu_item = None
        self.auto_send_check = None
        self.ai_check = None

        if self.config.get("use_appindicator", True) and HAS_INDICATOR:
            try:
                self.indicator = AppIndicator.Indicator.new(
                    "dictate-daemon",
                    "audio-input-microphone",
                    AppIndicator.IndicatorCategory.APPLICATION_STATUS
                )
                self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            except Exception as e:
                logging.error(f"Error initializing AppIndicator: {e}")

        self.build_menu()

    def build_menu(self) -> None:
        """Construct the system tray context menu."""
        menu = Gtk.Menu()

        self.status_menu_item = Gtk.MenuItem(label=self.i18n.t("loading_model"))
        self.status_menu_item.set_sensitive(False)
        menu.append(self.status_menu_item)
        menu.append(Gtk.SeparatorMenuItem())

        # Whisper Model selection sub-menu
        model_menu_item = Gtk.MenuItem(label=self.i18n.t("whisper_model"))
        model_submenu = Gtk.Menu()
        model_menu_item.set_submenu(model_submenu)

        current_model = self.config.get("whisper_model_size", "medium")
        group = None
        for size in ["tiny", "base", "small", "medium", "large-v3"]:
            radio = Gtk.RadioMenuItem.new_with_label(group, size)
            group = radio.get_group()
            if current_model == size:
                radio.set_active(True)
            radio.connect('toggled', self._on_model_toggled, size)
            model_submenu.append(radio)

        menu.append(model_menu_item)
        menu.append(Gtk.SeparatorMenuItem())

        # CheckToggles
        self.auto_send_check = Gtk.CheckMenuItem(label=self.i18n.t("auto_send"))
        self.auto_send_check.set_active(self.config.get("auto_send", False))
        self.auto_send_check.connect("toggled", lambda w: self.on_toggle_auto_send(w.get_active()))
        menu.append(self.auto_send_check)

        self.ai_check = Gtk.CheckMenuItem(label=self.i18n.t("ai_cleanup"))
        self.ai_check.set_active(self.config.get("ai_enabled", False))
        self.ai_check.connect("toggled", lambda w: self.on_toggle_ai(w.get_active()))
        menu.append(self.ai_check)

        menu.append(Gtk.SeparatorMenuItem())

        # OpenDeck installer item
        opendeck_plugin_path = os.path.expanduser("~/.config/opendeck/plugins/com.kirulab.dictate.sdplugin")
        plugin_installed = os.path.exists(opendeck_plugin_path)
        opendeck_label = self.i18n.t("opendeck_installed") if plugin_installed else self.i18n.t("opendeck_not_installed")
        item_opendeck = Gtk.MenuItem(label=opendeck_label)
        item_opendeck.connect('activate', self._install_opendeck_plugin)
        menu.append(item_opendeck)

        menu.append(Gtk.SeparatorMenuItem())

        # Config & Quit
        item_config = Gtk.MenuItem(label=self.i18n.t("settings"))
        item_config.connect('activate', lambda w: self.on_open_config())
        menu.append(item_config)

        menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label=self.i18n.t("quit"))
        item_quit.connect('activate', lambda w: self.on_quit())
        menu.append(item_quit)

        menu.show_all()
        if HAS_INDICATOR and self.indicator:
            self.indicator.set_menu(menu)

    def set_status_text(self, text: str) -> None:
        """Update system tray menu header status label."""
        if self.status_menu_item:
            self.status_menu_item.set_label(text)

    def _on_model_toggled(self, widget: Gtk.RadioMenuItem, size: str) -> None:
        if widget.get_active():
            self.on_model_change(size)

    def _install_opendeck_plugin(self, widget: Gtk.MenuItem) -> None:
        opendeck_plugins_dir = os.path.expanduser("~/.config/opendeck/plugins/")
        plugin_name = "com.kirulab.dictate.sdplugin"
        target_dir = os.path.join(opendeck_plugins_dir, plugin_name)
        source_dir = os.path.join(os.path.expanduser("~/.local/share/dictate-whisper"), "plugins", plugin_name)
        if not os.path.exists(source_dir):
            source_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins", plugin_name)

        try:
            os.makedirs(opendeck_plugins_dir, exist_ok=True)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            if os.path.exists(source_dir):
                shutil.copytree(source_dir, target_dir)
                logging.info(f"OpenDeck plugin copied to {target_dir}")

                subprocess.run(["pkill", "-9", "opendeck"])
                subprocess.Popen(["/usr/bin/opendeck", "--hide"], start_new_session=True)

                self.show_notification(self.i18n.t("opendeck"), self.i18n.t("opendeck_installed_success"))
                widget.set_label(self.i18n.t("opendeck_installed"))
            else:
                self.show_notification(self.i18n.t("error"), self.i18n.t("error_plugin_not_found"))
        except Exception as e:
            logging.error(f"Error installing OpenDeck plugin: {e}", exc_info=True)
            self.show_notification(self.i18n.t("error"), str(e))

"""
Update Notification & Management Window for OpenDictate.

Renders modern GTK3 dark-themed modal dialog displaying version comparisons,
release notes from GitHub API, and user-space 1-click update execution.
"""

import os
import webbrowser
import logging
from typing import Dict, Any, Optional, Callable

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from core.__version__ import __version__
from i18n import get_translator


UPDATE_DIALOG_CSS = b"""
/* OpenDictate Update Dialog Modern Dark UI */
window.update-window {
    background-color: #1e1e1e;
    color: #e0e0e0;
}

.update-header {
    background-color: #161616;
    padding: 16px 20px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.update-title {
    font-size: 16px;
    font-weight: bold;
    color: #ffffff;
}

.update-subtitle {
    font-size: 12px;
    color: #999999;
}

.version-badge-container {
    background-color: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 10px 16px;
    margin: 12px 18px 6px 18px;
}

.badge-current {
    font-size: 12px;
    color: #aaaaaa;
}

.badge-new {
    font-size: 13px;
    font-weight: bold;
    color: #57e389;
}

.badge-prerelease {
    background-color: rgba(246, 211, 45, 0.15);
    color: #f6d32d;
    border: 1px solid rgba(246, 211, 45, 0.35);
    border-radius: 4px;
    font-size: 10px;
    font-weight: bold;
    padding: 1px 6px;
}

.notes-container {
    background-color: #141414;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    margin: 6px 18px 12px 18px;
    padding: 10px;
}

.notes-textview {
    background-color: transparent;
    color: #d8d8d8;
    font-size: 12px;
    font-family: monospace;
}

.notes-label {
    font-size: 11px;
    font-weight: bold;
    color: #888888;
    margin-left: 18px;
    margin-top: 6px;
}

.notice-box {
    background-color: rgba(53, 132, 228, 0.1);
    border: 1px solid rgba(53, 132, 228, 0.3);
    border-radius: 6px;
    padding: 8px 12px;
    margin: 6px 18px;
}

.notice-text {
    font-size: 11px;
    color: #99c1f1;
}

.status-label {
    font-size: 12px;
    color: #3584e4;
    font-weight: 500;
}

.btn-suggested {
    background-color: #3584e4;
    color: #ffffff;
    font-weight: bold;
    border-radius: 6px;
    padding: 6px 16px;
}

.btn-suggested:hover {
    background-color: #1c71d8;
}
"""


class UpdateDialog(Gtk.Window):
    """Modern GTK3 update notification window displaying release details."""

    def __init__(
        self,
        config: Dict[str, Any],
        config_manager: Any,
        update_info: Dict[str, Any],
        is_user_install: bool = False,
        on_close: Optional[Callable[[], None]] = None
    ) -> None:
        """Initialize Update Dialog window.

        Args:
            config: Application configuration dictionary.
            config_manager: ConfigManager instance.
            update_info: Dictionary with 'version', 'url', 'notes', and optional 'assets'.
            is_user_install: Flag indicating whether app is installed in ~/.local/share/opendictate.
            on_close: Optional callback invoked when the window closes.
        """
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.config = config
        self.config_manager = config_manager
        self.update_info = update_info
        self.is_user_install = is_user_install
        self.on_close = on_close

        lang = self.config.get("ui_language", "es")
        self.i18n = get_translator(lang)

        self.set_title(self.i18n.t("update_dialog_title"))
        self.set_default_size(520, 480)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(False)
        self.get_style_context().add_class("update-window")

        self._apply_css()
        self._build_ui()

    def _apply_css(self) -> None:
        """Load and apply custom dark CSS styling."""
        provider = Gtk.CssProvider()
        provider.load_from_data(UPDATE_DIALOG_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self) -> None:
        """Construct the update dialog UI layout."""
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main_box)

        # 1. Header Box
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        header_box.get_style_context().add_class("update-header")

        icon = Gtk.Image.new_from_icon_name("software-update-available", Gtk.IconSize.DIALOG)
        header_box.pack_start(icon, False, False, 0)

        title_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_lbl = Gtk.Label(label=self.i18n.t("update_dialog_title"), xalign=0)
        title_lbl.get_style_context().add_class("update-title")
        subtitle_lbl = Gtk.Label(label=self.i18n.t("update_dialog_subtitle"), xalign=0)
        subtitle_lbl.get_style_context().add_class("update-subtitle")

        title_vbox.pack_start(title_lbl, False, False, 0)
        title_vbox.pack_start(subtitle_lbl, False, False, 0)
        header_box.pack_start(title_vbox, True, True, 0)
        main_box.pack_start(header_box, False, False, 0)

        # 2. Version Comparison Badge
        badge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        badge_box.get_style_context().add_class("version-badge-container")

        cur_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        cur_title = Gtk.Label(label=self.i18n.t("update_lbl_current_version"), xalign=0)
        cur_title.get_style_context().add_class("badge-current")
        cur_val = Gtk.Label(label=f"v{__version__}", xalign=0)
        cur_val.get_style_context().add_class("row-title")
        cur_box.pack_start(cur_title, False, False, 0)
        cur_box.pack_start(cur_val, False, False, 0)
        badge_box.pack_start(cur_box, True, True, 0)

        arrow_lbl = Gtk.Label(label="➔")
        arrow_lbl.get_style_context().add_class("badge-current")
        badge_box.pack_start(arrow_lbl, False, False, 0)

        new_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        new_title = Gtk.Label(label=self.i18n.t("update_lbl_new_version"), xalign=0)
        new_title.get_style_context().add_class("badge-current")
        
        if self.update_info.get("is_prerelease") or self.update_info.get("channel") == "nightly":
            new_title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            new_title_box.pack_start(new_title, False, False, 0)
            pre_badge = Gtk.Label(label="NIGHTLY / PRE-RELEASE")
            pre_badge.get_style_context().add_class("badge-prerelease")
            new_title_box.pack_start(pre_badge, False, False, 0)
            new_box.pack_start(new_title_box, False, False, 0)
        else:
            new_box.pack_start(new_title, False, False, 0)

        new_ver_str = self.update_info.get("version", "")
        new_val = Gtk.Label(label=f"v{new_ver_str}", xalign=0)
        new_val.get_style_context().add_class("badge-new")
        new_box.pack_start(new_val, False, False, 0)
        badge_box.pack_start(new_box, True, True, 0)

        main_box.pack_start(badge_box, False, False, 0)

        # 3. Environment Notice if non-user installation
        if not self.is_user_install:
            notice_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            notice_box.get_style_context().add_class("notice-box")
            notice_lbl = Gtk.Label(
                label=self.i18n.t("update_dev_mode_notice"),
                xalign=0,
                wrap=True
            )
            notice_lbl.get_style_context().add_class("notice-text")
            notice_box.pack_start(notice_lbl, True, True, 0)
            main_box.pack_start(notice_box, False, False, 0)

        # 4. Release Notes Label & Scrolled Box
        notes_hdr = Gtk.Label(label=self.i18n.t("update_lbl_release_notes"), xalign=0)
        notes_hdr.get_style_context().add_class("notes-label")
        main_box.pack_start(notes_hdr, False, False, 0)

        notes_scroll = Gtk.ScrolledWindow()
        notes_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        notes_scroll.get_style_context().add_class("notes-container")
        notes_scroll.set_size_request(-1, 160)

        self.notes_view = Gtk.TextView()
        self.notes_view.set_editable(False)
        self.notes_view.set_cursor_visible(False)
        self.notes_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.notes_view.get_style_context().add_class("notes-textview")

        raw_notes = self.update_info.get("notes", "") or "No release notes provided."
        buffer = self.notes_view.get_buffer()
        buffer.set_text(raw_notes)

        notes_scroll.add(self.notes_view)
        main_box.pack_start(notes_scroll, True, True, 0)

        # 5. Progress / Status Section (Hidden by default)
        self.status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.status_box.set_margin_start(18)
        self.status_box.set_margin_end(18)
        self.status_box.set_margin_bottom(6)
        self.status_box.set_no_show_all(True)

        self.spinner = Gtk.Spinner()
        self.status_label = Gtk.Label(label="", xalign=0)
        self.status_label.get_style_context().add_class("status-label")

        self.status_box.pack_start(self.spinner, False, False, 0)
        self.status_box.pack_start(self.status_label, True, True, 0)
        main_box.pack_start(self.status_box, False, False, 0)

        # 6. Bottom Action Buttons Bar
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        actions_box.set_margin_start(18)
        actions_box.set_margin_end(18)
        actions_box.set_margin_top(8)
        actions_box.set_margin_bottom(16)

        self.remind_btn = Gtk.Button(label=self.i18n.t("update_btn_remind_later"))
        self.remind_btn.connect("clicked", self._on_remind_later)
        actions_box.pack_start(self.remind_btn, False, False, 0)

        self.github_btn = Gtk.Button(label=self.i18n.t("update_btn_open_github"))
        self.github_btn.connect("clicked", self._on_open_github)
        actions_box.pack_start(self.github_btn, False, False, 0)

        actions_box.pack_start(Gtk.Box(), True, True, 0)  # Spacer

        if self.is_user_install:
            self.update_btn = Gtk.Button(label=self.i18n.t("update_btn_update_now"))
            self.update_btn.get_style_context().add_class("btn-suggested")
            self.update_btn.connect("clicked", self._on_update_now)
            actions_box.pack_end(self.update_btn, False, False, 0)
        else:
            self.close_btn = Gtk.Button(label=self.i18n.t("update_btn_close"))
            self.close_btn.connect("clicked", lambda b: self.destroy())
            actions_box.pack_end(self.close_btn, False, False, 0)

        main_box.pack_start(actions_box, False, False, 0)

    def _on_remind_later(self, btn: Gtk.Button) -> None:
        """Mark the current update version as dismissed in SQLite config and close."""
        target_version = self.update_info.get("version", "")
        if target_version:
            self.config["update_dismissed_version"] = target_version
            self.config_manager.save_config(self.config)
        self.destroy()

    def _on_open_github(self, btn: Gtk.Button) -> None:
        """Open the release webpage in default browser."""
        url = self.update_info.get("url", "https://github.com/ThePartyAcolyte/opendictate/releases/latest")
        try:
            webbrowser.open(url)
        except Exception as e:
            logging.error(f"Error opening browser: {e}")

    def _on_update_now(self, btn: Gtk.Button) -> None:
        """Trigger automated in-app update for user installation."""
        from core.updater import perform_user_update

        # Lock UI buttons
        self.remind_btn.set_sensitive(False)
        self.github_btn.set_sensitive(False)
        if hasattr(self, 'update_btn'):
            self.update_btn.set_sensitive(False)

        # Show status spinner
        self.status_box.show()
        self.spinner.start()
        self.status_label.set_text(self.i18n.t("update_status_downloading"))

        def _progress_cb(status_text: str) -> None:
            GLib.idle_add(self.status_label.set_text, status_text)

        def _complete_cb(success: bool, msg: str) -> None:
            def _ui():
                self.spinner.stop()
                if success:
                    self.status_label.set_text(self.i18n.t("update_status_success"))
                    GLib.timeout_add(1500, self._on_update_finished_restart)
                else:
                    err_msg = self.i18n.t("update_status_error", error=msg)
                    self.status_label.set_text(err_msg)
                    self.remind_btn.set_sensitive(True)
                    self.github_btn.set_sensitive(True)
                    if hasattr(self, 'update_btn'):
                        self.update_btn.set_sensitive(True)
                return False
            GLib.idle_add(_ui)

        perform_user_update(self.config, self.update_info, _progress_cb, _complete_cb)

    def _on_update_finished_restart(self) -> None:
        """Restart OpenDictate daemon service after successful update and close dialog."""
        from core.updater import restart_opendictate_service
        self.destroy()
        restart_opendictate_service()


def show_update_dialog(
    config: Dict[str, Any],
    config_manager: Any,
    update_info: Dict[str, Any]
) -> UpdateDialog:
    """Instantiate and show the Update Dialog on the active GTK display.

    Args:
        config: Application configuration dictionary.
        config_manager: ConfigManager instance.
        update_info: Release information dictionary.

    Returns:
        The instantiated UpdateDialog window.
    """
    from core.updater import is_user_installation
    is_user_install = is_user_installation()
    dialog = UpdateDialog(
        config=config,
        config_manager=config_manager,
        update_info=update_info,
        is_user_install=is_user_install
    )
    dialog.show_all()
    dialog.present()
    return dialog

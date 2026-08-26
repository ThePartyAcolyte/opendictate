#!/usr/bin/env python3
"""
GTK Configuration Window UI module for OpenDictate.

Renders modern vertical sidebar settings window for General settings,
AI Model settings, Application Profiles, Advanced STT/Chunking engine,
and Whisper Model Manager.
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import sqlite3
import json
import os
import subprocess
import re
import shutil
from typing import Dict, Any, Optional, Callable, Tuple, List
from i18n import get_translator
from core.config import ConfigManager
from core.hardware import detect_desktop_environment, is_cuda_runtime_ready, get_cpu_core_count, get_supported_compute_types


SETTINGS_CSS = b"""
/* OpenDictate Settings Modern Dark UI */
window.opendictate-settings {
    background-color: #1e1e1e;
    color: #e0e0e0;
}

.sidebar-panel {
    background-color: #161616;
    border-right: 1px solid rgba(255, 255, 255, 0.08);
}

.sidebar-panel list {
    background-color: transparent;
}

.sidebar-panel row {
    padding: 10px 14px;
    margin: 3px 8px;
    border-radius: 8px;
    color: #a0a0a0;
    font-weight: 500;
    font-size: 13px;
    transition: all 150ms ease;
}

.sidebar-panel row:hover {
    background-color: rgba(255, 255, 255, 0.05);
    color: #ffffff;
}

.sidebar-panel row:selected {
    background-color: rgba(255, 255, 255, 0.12);
    color: #ffffff;
    font-weight: bold;
}

.page-container {
    padding: 18px 24px;
}

.card-frame {
    background-color: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 10px;
    margin-bottom: 16px;
    padding: 2px;
}

.card-list {
    background-color: transparent;
}

.preference-row {
    padding: 8px 12px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.preference-row:last-child {
    border-bottom: none;
}

.section-title {
    font-size: 11px;
    font-weight: bold;
    color: #888888;
    margin-bottom: 6px;
    margin-top: 8px;
    letter-spacing: 0.6px;
}

.row-title {
    font-size: 13px;
    font-weight: 500;
    color: #f0f0f0;
}

.row-subtitle {
    font-size: 11px;
    color: #888888;
}

.badge-downloaded {
    color: #57e389;
    font-weight: bold;
}

.badge-not-downloaded {
    color: #777777;
}
"""



class AppProfilesDialog(Gtk.Dialog):
    def __init__(self, parent, config, db_path, i18n, auto_save_cb):
        super().__init__(title=i18n.t("tab_apps"), transient_for=parent, flags=0)
        self.config = config
        self.db_path = db_path
        self.i18n = i18n
        self.auto_save_cb = auto_save_cb
        self.current_selected_app = None
        self._updating_ui = False
        
        self.set_default_size(700, 500)
        
        profiles_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        profiles_box.set_margin_top(14)
        profiles_box.set_margin_bottom(14)
        profiles_box.set_margin_left(14)
        profiles_box.set_margin_right(14)
        
        # Left: Profiles List
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left_box.set_size_request(220, -1)
        profiles_box.pack_start(left_box, False, False, 0)

        left_card_frame = Gtk.Frame()
        left_card_frame.get_style_context().add_class("card-frame")
        left_card_frame.set_shadow_type(Gtk.ShadowType.NONE)

        self.listbox = Gtk.ListBox()
        self.listbox.get_style_context().add_class("card-list")
        self.listbox.connect("row-selected", self.on_app_selected)
        scroll_list = Gtk.ScrolledWindow()
        scroll_list.set_min_content_height(320)
        scroll_list.add(self.listbox)
        left_card_frame.add(scroll_list)
        left_box.pack_start(left_card_frame, True, True, 0)

        add_btn = Gtk.Button(label=self.i18n.t("btn_add_app"))
        add_btn.connect("clicked", self.on_add_app)
        left_box.pack_start(add_btn, False, False, 0)

        # Right: Profile Editor
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        profiles_box.pack_start(right_box, True, True, 0)

        self.current_app_label = Gtk.Label(xalign=0)
        self.current_app_label.set_markup(f"<span size='large' weight='bold'>{self.i18n.t('msg_select_app')}</span>")
        right_box.pack_start(self.current_app_label, False, False, 0)

        card_prof, list_prof = parent._create_card(self.i18n.t("lbl_sys_prompt"))

        self.prompt_view = Gtk.TextView()
        self.prompt_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.prompt_view.connect("focus-out-event", self.auto_save_profile)
        scroll_prompt = Gtk.ScrolledWindow()
        scroll_prompt.set_shadow_type(Gtk.ShadowType.IN)
        scroll_prompt.set_min_content_height(180)
        scroll_prompt.add(self.prompt_view)

        prof_row = Gtk.ListBoxRow()
        prof_row.get_style_context().add_class("preference-row")
        prof_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        prof_vbox.set_margin_top(6)
        prof_vbox.set_margin_bottom(6)
        prof_vbox.set_margin_left(8)
        prof_vbox.set_margin_right(8)
        prof_vbox.pack_start(scroll_prompt, True, True, 0)
        prof_row.add(prof_vbox)
        list_prof.add(prof_row)

        self.vision_switch = Gtk.CheckButton(label=self.i18n.t("lbl_vision"))
        self.vision_switch.connect("toggled", self.auto_save_profile)
        list_prof.add(parent._create_control_row(self.i18n.t("lbl_vision"), self.vision_switch))

        right_box.pack_start(card_prof, True, True, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        del_prof_btn = Gtk.Button(label=self.i18n.t("btn_delete"))
        del_prof_btn.connect("clicked", self.delete_current_profile)
        btn_box.pack_start(del_prof_btn, False, False, 0)
        right_box.pack_start(btn_box, False, False, 0)
        
        self.get_content_area().pack_start(profiles_box, True, True, 0)
        self.show_all()
        self.load_profiles()

    def load_profiles(self) -> None:
        for child in self.listbox.get_children():
            self.listbox.remove(child)

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT app_class FROM app_profiles")
            for row in cursor.fetchall():
                row_widget = Gtk.ListBoxRow()
                row_widget.get_style_context().add_class("preference-row")
                lbl = Gtk.Label(label=row[0], xalign=0, margin=10)
                lbl.get_style_context().add_class("row-title")
                row_widget.add(lbl)
                row_widget.app_class = row[0]
                self.listbox.add(row_widget)
            conn.close()
            self.listbox.show_all()
        except Exception as e:
            print("Error loading profiles:", e)


    def on_app_selected(self, listbox: Gtk.ListBox, row: Optional[Gtk.ListBoxRow]) -> None:
        if not row:
            self._updating_ui = True
            self.current_selected_app = None
            self.current_app_label.set_markup(f"<span size='large' weight='bold'>{self.i18n.t('msg_select_app')}</span>")
            self.prompt_view.get_buffer().set_text("")
            self.vision_switch.set_active(False)
            self._updating_ui = False
            return

        self._updating_ui = True
        self.current_selected_app = row.app_class
        title_text = self.i18n.t("lbl_current_profile", self.current_selected_app)
        escaped_title = GLib.markup_escape_text(title_text)
        self.current_app_label.set_markup(f"<span size='large' weight='bold'>{escaped_title}</span>")

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT system_prompt, enable_vision FROM app_profiles WHERE app_class = ?", (self.current_selected_app,))
            data = cursor.fetchone()
            conn.close()

            if data:
                self.prompt_view.get_buffer().set_text(data[0] if data[0] else "")
                self.vision_switch.set_active(bool(data[1]))
        except Exception as e:
            print("Error loading profile details:", e)
        self._updating_ui = False


    def get_open_apps(self) -> List[str]:
        apps = set()
        try:
            import pyatspi
            desktop = pyatspi.Registry.getDesktop(0)
            for app in desktop:
                if not app:
                    continue
                if app.name:
                    window_name = ""
                    for window in app:
                        if window and window.name:
                            window_name = window.name
                            break
                    if window_name:
                        apps.add(f"{window_name} [{app.name}]")
                    else:
                        apps.add(f"{app.name} [{app.name}]")
        except Exception:
            pass
        return sorted(list(apps))


    def on_add_app(self, btn: Gtk.Button) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=self.i18n.t("dialog_new_app_title")
        )
        dialog.format_secondary_text(self.i18n.t("dialog_new_app_msg"))

        combo = Gtk.ComboBoxText.new_with_entry()
        for app in self.get_open_apps():
            combo.append_text(app)

        dialog.get_message_area().pack_start(combo, False, False, 0)
        dialog.show_all()

        response = dialog.run()
        raw_text = combo.get_child().get_text().strip()
        dialog.destroy()

        app_name = raw_text
        if raw_text:
            match = re.search(r'\[(.*?)\]$', raw_text)
            if match:
                app_name = match.group(1).strip()

        if response == Gtk.ResponseType.OK and app_name:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO app_profiles (app_class, system_prompt, enable_vision) VALUES (?, '', 0)",
                    (app_name,)
                )
                conn.commit()
                conn.close()
                self.load_profiles()
            except Exception as e:
                self.show_message(self.i18n.t("error", ""), str(e))


    def auto_save_profile(self, *args) -> None:
        if self._updating_ui or not self.current_selected_app:
            return

        buffer = self.prompt_view.get_buffer()
        start, end = buffer.get_bounds()
        prompt = buffer.get_text(start, end, True).strip()
        vision = 1 if self.vision_switch.get_active() else 0

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE app_profiles SET system_prompt = ?, enable_vision = ? WHERE app_class = ?",
                (prompt, vision, self.current_selected_app)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print("Auto-save profile error:", e)


    def delete_current_profile(self, btn: Gtk.Button) -> None:
        if not self.current_selected_app:
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM app_profiles WHERE app_class = ?", (self.current_selected_app,))
            conn.commit()
            conn.close()
            self.load_profiles()
            self.on_app_selected(self.listbox, None)
        except Exception as e:
            self.show_message(self.i18n.t("error", ""), str(e))



    def show_message(self, title: str, message: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=title
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

class ConfigWindow(Gtk.Window):
    """GTK Settings and Profile management window."""

    def __init__(
        self,
        db_path: str,
        config_path: str,
        on_config_saved: Optional[Callable[[Optional[Dict[str, Any]]], None]] = None,
        daemon_ref: Optional[Any] = None
    ) -> None:
        self.db_path = db_path
        self.config_path = config_path
        self.on_config_saved = on_config_saved
        self.daemon_ref = daemon_ref
        
        self.config_manager = ConfigManager()
        self.config = self.load_config()
        self.i18n = get_translator(self.config.get("ui_language", "en"))
        
        self._updating_ui = False

        super().__init__(title=self.i18n.t("settings_title"))
        self.set_default_size(800, 540)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.get_style_context().add_class("opendictate-settings")
        self.connect("delete-event", self.on_delete_event)
        
        self._apply_css()
        self._build_ui()

    def _build_ui(self) -> None:
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.add(main_box)

        # Vertical Sidebar + Stack layout
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(150)

        self.sidebar = Gtk.StackSidebar()
        self.sidebar.set_stack(self.stack)
        self.sidebar.set_size_request(200, -1)
        self.sidebar.get_style_context().add_class("sidebar-panel")
        main_box.pack_start(self.sidebar, False, False, 0)
        main_box.pack_start(self.stack, True, True, 0)

        # ---------------------------------------------------------
        # Tab 1: General
        # ---------------------------------------------------------
        general_scroll = Gtk.ScrolledWindow()
        general_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        general_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        general_box.get_style_context().add_class("page-container")
        general_scroll.add(general_box)
        self.stack.add_titled(general_scroll, "general", self.i18n.t("tab_general"))

        # Card 1: Interface & System (Language selection at the top)
        card_iface, list_iface = self._create_card(self.i18n.t("group_interface_system"))

        self.ui_lang_combo = Gtk.ComboBoxText()
        self.ui_lang_combo.append("en", "English")
        self.ui_lang_combo.append("es", "Español")
        self.ui_lang_combo.append("fr", "Français")
        self.ui_lang_combo.append("de", "Deutsch")
        self.ui_lang_combo.set_active_id(self.config.get("ui_language", "en"))
        self.ui_lang_combo.connect("changed", self.on_ui_language_changed)
        list_iface.add(self._create_control_row(self.i18n.t("ui_language"), self.ui_lang_combo))

        from core.hardware import detect_desktop_environment
        _, is_gnome = detect_desktop_environment()

        self.indicator_combo = Gtk.ComboBoxText()
        self.indicator_combo.append("auto", self.i18n.t("indicator_mode_auto"))
        if is_gnome:
            self.indicator_combo.append("gnome_ext", self.i18n.t("indicator_mode_gnome"))
        else:
            self.indicator_combo.append("gnome_ext", f"{self.i18n.t('indicator_mode_gnome')} ({self.i18n.t('indicator_gnome_unavailable')})")
        self.indicator_combo.append("tray", self.i18n.t("indicator_mode_tray"))
        self.indicator_combo.append("none", self.i18n.t("indicator_mode_none"))

        curr_mode = self.config.get("indicator_mode", "auto")
        self.indicator_combo.set_active_id(curr_mode)
        self.indicator_combo.connect("changed", self.on_indicator_mode_changed)
        list_iface.add(self._create_control_row(self.i18n.t("lbl_indicator_mode"), self.indicator_combo))

        self.hide_bubble_switch = Gtk.Switch()
        self.hide_bubble_switch.set_active(self.config.get("hide_bubble", False))
        self.hide_bubble_switch.connect("notify::active", self._on_hide_bubble_changed)
        list_iface.add(self._create_switch_row(self.i18n.t("lbl_hide_bubble"), self.hide_bubble_switch))

        self.bubble_mode_combo = Gtk.ComboBoxText()
        self.bubble_mode_combo.append("auto", self.i18n.t("bubble_mode_auto"))
        self.bubble_mode_combo.append("text", self.i18n.t("bubble_mode_text"))
        self.bubble_mode_combo.append("interactive", self.i18n.t("bubble_mode_interactive"))
        self.bubble_mode_combo.set_active_id(self.config.get("bubble_mode", "auto"))
        self.bubble_mode_combo.set_sensitive(not self.hide_bubble_switch.get_active())
        self.bubble_mode_combo.connect("changed", self.auto_save)
        list_iface.add(self._create_control_row(self.i18n.t("lbl_bubble_mode"), self.bubble_mode_combo))

        self.btn_run_wizard = Gtk.Button(label=self.i18n.t("btn_launch_wizard"))
        self.btn_run_wizard.connect("clicked", self.on_launch_wizard_clicked)
        list_iface.add(self._create_control_row(self.i18n.t("lbl_launch_wizard"), self.btn_run_wizard, self.i18n.t("lbl_launch_wizard_desc")))

        general_box.pack_start(card_iface, False, False, 0)

        # Card 2: Dictation Behavior
        card_dict, list_dict = self._create_card(self.i18n.t("group_dictation_behavior"))
        
        self.auto_send_switch = Gtk.Switch()
        self.auto_send_switch.set_active(self.config.get("auto_send", False))
        self.auto_send_switch.connect("notify::active", self.auto_save)
        list_dict.add(self._create_switch_row(self.i18n.t("lbl_autosend"), self.auto_send_switch))

        self.ai_enabled_switch = Gtk.Switch()
        self.ai_enabled_switch.set_active(self.config.get("ai_enabled", False))
        self.ai_enabled_switch.connect("notify::active", self.auto_save)
        list_dict.add(self._create_switch_row(self.i18n.t("lbl_ai_enabled"), self.ai_enabled_switch))

        self.restore_focus_switch = Gtk.Switch()
        self.restore_focus_switch.set_active(self.config.get("restore_window_focus", False))
        self.restore_focus_switch.connect("notify::active", self.auto_save)
        list_dict.add(self._create_switch_row(self.i18n.t("lbl_restore_focus"), self.restore_focus_switch))

        self.auto_pause_switch = Gtk.Switch()
        self.auto_pause_switch.set_active(self.config.get("auto_pause_media", True))
        self.auto_pause_switch.connect("notify::active", self.auto_save)
        list_dict.add(self._create_switch_row(self.i18n.t("lbl_auto_pause"), self.auto_pause_switch))

        self.notifications_switch = Gtk.Switch()
        self.notifications_switch.set_active(self.config.get("show_notifications", True))
        self.notifications_switch.connect("notify::active", self.auto_save)
        list_dict.add(self._create_switch_row(self.i18n.t("lbl_notifications"), self.notifications_switch))

        self.autostart_switch = Gtk.Switch()
        autostart_path = os.path.expanduser("~/.config/autostart/opendictate.desktop")
        self.autostart_switch.set_active(os.path.exists(autostart_path))
        self.autostart_switch.connect("notify::active", self.auto_save)
        list_dict.add(self._create_switch_row(self.i18n.t("lbl_autostart"), self.autostart_switch))

        general_box.pack_start(card_dict, False, False, 0)

        # Card 3: Updates
        card_updates, list_updates = self._create_card(self.i18n.t("group_updates"))

        self.check_updates_switch = Gtk.Switch()
        self.check_updates_switch.set_active(self.config.get("check_updates", False))
        self.check_updates_switch.connect("notify::active", self._on_check_updates_changed)
        list_updates.add(self._create_switch_row(self.i18n.t("lbl_check_updates"), self.check_updates_switch))

        self.update_freq_combo = Gtk.ComboBoxText()
        self.update_freq_combo.append("daily", self.i18n.t("freq_daily"))
        self.update_freq_combo.append("weekly", self.i18n.t("freq_weekly"))
        self.update_freq_combo.append("monthly", self.i18n.t("freq_monthly"))
        self.update_freq_combo.set_active_id(self.config.get("update_frequency", "monthly"))
        self.update_freq_combo.set_sensitive(self.check_updates_switch.get_active())
        self.update_freq_combo.connect("changed", self.auto_save)
        list_updates.add(self._create_control_row(self.i18n.t("lbl_update_frequency"), self.update_freq_combo))

        # Manual check button
        check_btn_row = Gtk.ListBoxRow()
        check_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        check_btn_box.set_margin_start(16)
        check_btn_box.set_margin_end(16)
        check_btn_box.set_margin_top(12)
        check_btn_box.set_margin_bottom(12)
        
        self.manual_check_btn = Gtk.Button(label=self.i18n.t("btn_check_updates_now"))
        self.manual_check_btn.connect("clicked", self._on_manual_check_updates)
        check_btn_box.pack_start(self.manual_check_btn, True, True, 0)
        
        check_btn_row.add(check_btn_box)
        list_updates.add(check_btn_row)

        general_box.pack_start(card_updates, False, False, 0)

        # ---------------------------------------------------------
        # Tab 2: AI & Models
        # ---------------------------------------------------------
        ai_scroll = Gtk.ScrolledWindow()
        ai_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        ai_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        ai_box.get_style_context().add_class("page-container")
        ai_scroll.add(ai_box)
        self.stack.add_titled(ai_scroll, "ai", self.i18n.t("tab_ai"))

        # Card: API Configuration
        card_api, list_api = self._create_card(self.i18n.t("group_api_credentials"))

        self.api_key_entry = Gtk.Entry()
        self.api_key_entry.set_text(self.config.get("api_key", ""))
        self.api_key_entry.set_visibility(False)
        self.api_key_entry.set_width_chars(28)
        self.api_key_entry.connect("focus-out-event", self.auto_save)
        list_api.add(self._create_control_row(self.i18n.t("lbl_api_key"), self.api_key_entry))

        self.model_entry = Gtk.Entry()
        self.model_entry.set_text(self.config.get("model", "gemma-4-26b-a4b-it"))
        self.model_entry.set_width_chars(28)
        self.model_entry.connect("focus-out-event", self.auto_save)
        list_api.add(self._create_control_row(self.i18n.t("lbl_model"), self.model_entry))

        ai_box.pack_start(card_api, False, False, 0)

        # Card: LLM Parameters
        card_llm, list_llm = self._create_card(self.i18n.t("group_llm_parameters"))

        self.llm_timeout_spin = Gtk.SpinButton.new_with_range(30, 600, 10)
        self.llm_timeout_spin.set_value(self.config.get("llm_timeout", 120))
        self.llm_timeout_spin.connect("value-changed", self.auto_save)
        list_llm.add(self._create_control_row(self.i18n.t("lbl_llm_timeout"), self.llm_timeout_spin))

        self.llm_temp_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 2.0, 0.1)
        self.llm_temp_scale.set_value(self.config.get("llm_temperature", 0.7))
        self.llm_temp_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.llm_temp_scale.set_size_request(160, -1)
        self.llm_temp_scale.connect("value-changed", self.auto_save)
        list_llm.add(self._create_control_row(self.i18n.t("lbl_llm_temp"), self.llm_temp_scale))

        self.llm_thinking_switch = Gtk.Switch()
        self.llm_thinking_switch.set_active(self.config.get("llm_thinking", False))
        self.llm_thinking_switch.connect("notify::active", self.auto_save)
        list_llm.add(self._create_switch_row(self.i18n.t("lbl_llm_thinking"), self.llm_thinking_switch))

        ai_box.pack_start(card_llm, False, False, 0)

        # Card: Base System Prompt
        card_prompt, list_prompt = self._create_card(self.i18n.t("group_system_prompt"))
        
        self.base_prompt_view = Gtk.TextView()
        self.base_prompt_view.set_wrap_mode(Gtk.WrapMode.WORD)
        default_base_prompt = (
            "You are a real-time voice dictation assistant.\n"
            "Your objective is to clean up the following voice-dictated text, "
            "correcting obvious speech recognition errors and punctuation, "
            "while keeping it as faithful to the original as possible.\n"
            "If the text includes verbal formatting instructions (e.g. 'open parenthesis', 'new line', 'comma', 'period'), apply them.\n"
            "Use capitalization when appropriate and correct homophones based on context to make sense of the text without changing the original words or adding extra text.\n"
            "CRITICAL: You MUST reply in the EXACT SAME LANGUAGE as the dictated text. Do not translate it. For example, if the input is in Spanish, output in Spanish.\n"
            "Return ONLY the corrected text, without greetings, explanations or translations."
        )
        self.base_prompt_view.get_buffer().set_text(self.config.get("base_system_prompt", default_base_prompt))
        self.base_prompt_view.connect("focus-out-event", self.auto_save)

        scroll_base_prompt = Gtk.ScrolledWindow()
        scroll_base_prompt.set_shadow_type(Gtk.ShadowType.IN)
        scroll_base_prompt.set_min_content_height(120)
        scroll_base_prompt.add(self.base_prompt_view)

        prompt_row = Gtk.ListBoxRow()
        prompt_row.get_style_context().add_class("preference-row")
        prompt_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        prompt_box.set_margin_top(6)
        prompt_box.set_margin_bottom(6)
        prompt_box.set_margin_left(8)
        prompt_box.set_margin_right(8)
        prompt_box.pack_start(scroll_base_prompt, True, True, 0)
        prompt_row.add(prompt_box)
        list_prompt.add(prompt_row)

                
        self.manage_apps_btn = Gtk.Button(label=self.i18n.t("tab_apps"))
        self.manage_apps_btn.connect("clicked", self.on_manage_apps_clicked)
        list_prompt.add(self._create_control_row("", self.manage_apps_btn))

        ai_box.pack_start(card_prompt, False, False, 0)


        # ---------------------------------------------------------
        # Tab 4: Engine & Advanced (Avanzado)
        # ---------------------------------------------------------
        adv_scroll = Gtk.ScrolledWindow()
        adv_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        adv_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        adv_box.get_style_context().add_class("page-container")
        adv_scroll.add(adv_box)
        self.stack.add_titled(adv_scroll, "advanced", self.i18n.t("tab_advanced"))

        # Card 1: Real-Time Chunking Engine (Master switch + dependent tuning params)
        card_chunk, list_chunk = self._create_card(self.i18n.t("group_chunking_engine"))

        self.realtime_switch = Gtk.Switch()
        self.realtime_switch.set_active(self.config.get("realtime_mode", True))
        self.realtime_switch.connect("notify::active", self._on_realtime_switch_changed)
        list_chunk.add(self._create_switch_row(self.i18n.t("lbl_realtime"), self.realtime_switch))

        # Container for dependent chunk options
        self.chunk_options_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self.chunk_silence_spin = Gtk.SpinButton.new_with_range(0.2, 3.0, 0.1)
        self.chunk_silence_spin.set_value(self.config.get("chunk_silence_duration", 0.6))
        self.chunk_silence_spin.connect("value-changed", self.auto_save)
        self.chunk_options_box.pack_start(
            self._create_control_row(self.i18n.t("lbl_chunk_silence"), self.chunk_silence_spin),
            False, False, 0
        )

        self.chunk_max_spin = Gtk.SpinButton.new_with_range(5.0, 60.0, 1.0)
        self.chunk_max_spin.set_value(self.config.get("chunk_max_duration", 30.0))
        self.chunk_max_spin.connect("value-changed", self.auto_save)
        self.chunk_options_box.pack_start(
            self._create_control_row(self.i18n.t("lbl_chunk_max"), self.chunk_max_spin),
            False, False, 0
        )

        self.chunk_fallback_silence_spin = Gtk.SpinButton.new_with_range(0.1, 2.0, 0.1)
        self.chunk_fallback_silence_spin.set_value(self.config.get("chunk_fallback_silence_duration", 0.4))
        self.chunk_fallback_silence_spin.connect("value-changed", self.auto_save)
        self.chunk_options_box.pack_start(
            self._create_control_row(self.i18n.t("lbl_chunk_fallback_silence"), self.chunk_fallback_silence_spin),
            False, False, 0
        )

        self.chunk_min_spin = Gtk.SpinButton.new_with_range(1.0, 10.0, 0.5)
        self.chunk_min_spin.set_value(self.config.get("chunk_min_duration", 3.0))
        self.chunk_min_spin.connect("value-changed", self.auto_save)
        self.chunk_options_box.pack_start(
            self._create_control_row(self.i18n.t("lbl_chunk_min"), self.chunk_min_spin),
            False, False, 0
        )

        chunk_opt_row = Gtk.ListBoxRow()
        chunk_opt_row.get_style_context().add_class("preference-row")
        chunk_opt_row.add(self.chunk_options_box)
        list_chunk.add(chunk_opt_row)

        # Apply initial sensitivity based on master switch state
        self.chunk_options_box.set_sensitive(self.realtime_switch.get_active())
        adv_box.pack_start(card_chunk, False, False, 0)

        # Card 2: Whisper STT Parameters
        card_stt, list_stt = self._create_card(self.i18n.t("group_stt_engine"))

        self.lang_combo = Gtk.ComboBoxText()
        self.lang_combo.append("auto", self.i18n.t("transcription_auto"))
        self.lang_combo.append("es", "Español")
        self.lang_combo.append("en", "English")
        self.lang_combo.append("fr", "Français")
        self.lang_combo.append("de", "Deutsch")
        self.lang_combo.append("it", "Italiano")
        self.lang_combo.append("pt", "Português")
        self.lang_combo.append("zh", "中文 (Chinese)")
        self.lang_combo.append("ja", "日本語 (Japanese)")
        self.lang_combo.append("ru", "Русский (Russian)")
        self.lang_combo.set_active_id(self.config.get("language", "auto"))
        self.lang_combo.connect("changed", self.auto_save)
        list_stt.add(self._create_control_row(self.i18n.t("transcription_language"), self.lang_combo))

        self.vad_switch = Gtk.Switch()
        self.vad_switch.set_active(self.config.get("vad_filter", False))
        self.vad_switch.connect("notify::active", self._on_vad_switch_changed)
        list_stt.add(self._create_switch_row(self.i18n.t("lbl_vad"), self.vad_switch))

        self.beam_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 10, 1)
        self.beam_scale.set_value(self.config.get("beam_size", 5))
        self.beam_scale.set_digits(0)
        self.beam_scale.set_size_request(160, -1)
        self.beam_scale.connect("value-changed", self.auto_save)
        list_stt.add(self._create_control_row(self.i18n.t("lbl_beam"), self.beam_scale))

        self.temp_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.1)
        self.temp_scale.set_value(self.config.get("temperature", 0.0))
        self.temp_scale.set_digits(1)
        self.temp_scale.set_size_request(160, -1)
        self.temp_scale.connect("value-changed", self.auto_save)
        list_stt.add(self._create_control_row(self.i18n.t("lbl_temp"), self.temp_scale))

        adv_box.pack_start(card_stt, False, False, 0)

        # Expander: Expert Whisper STT Parameters
        self.expert_expander = Gtk.Expander(label=f"<b>{self.i18n.t('expander_expert_whisper')}</b>")
        self.expert_expander.set_use_markup(True)
        self.expert_expander.set_margin_top(4)
        self.expert_expander.set_margin_bottom(4)

        expert_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)

        # Sub-Card 1: Hardware & Computation
        card_hw, list_hw = self._create_card(self.i18n.t("group_expert_hardware"))

        cuda_ready = is_cuda_runtime_ready()
        cpu_cores = get_cpu_core_count()

        self.device_combo = Gtk.ComboBoxText()
        self.device_combo.append("auto", self.i18n.t("device_auto"))
        self.device_combo.append("cpu", self.i18n.t("device_cpu"))
        if cuda_ready:
            self.device_combo.append("cuda", self.i18n.t("device_cuda"))

        curr_dev = self.config.get("whisper_device", "auto")
        if curr_dev == "cuda" and not cuda_ready:
            curr_dev = "auto"
            self.config["whisper_device"] = "auto"
        self.device_combo.set_active_id(curr_dev)
        self.device_combo.connect("changed", self._on_expert_device_changed)
        list_hw.add(self._create_control_row(self.i18n.t("lbl_whisper_device"), self.device_combo, self.i18n.t("desc_whisper_device")))

        self.compute_combo = Gtk.ComboBoxText()
        self._populate_compute_types(curr_dev)
        curr_compute = self.config.get("whisper_compute_type", "default")
        self.compute_combo.set_active_id(curr_compute)
        self.compute_combo.connect("changed", self.auto_save)
        list_hw.add(self._create_control_row(self.i18n.t("lbl_whisper_compute_type"), self.compute_combo, self.i18n.t("desc_whisper_compute_type")))

        self.cpu_threads_spin = Gtk.SpinButton.new_with_range(0, cpu_cores, 1)
        self.cpu_threads_spin.set_value(self.config.get("whisper_cpu_threads", 0))
        self.cpu_threads_spin.connect("value-changed", self.auto_save)
        list_hw.add(self._create_control_row(self.i18n.t("lbl_whisper_cpu_threads"), self.cpu_threads_spin, self.i18n.t("desc_whisper_cpu_threads")))

        expert_vbox.pack_start(card_hw, False, False, 0)

        # Sub-Card 2: Repetition & Hallucination Control
        card_anti_loop, list_anti_loop = self._create_card(self.i18n.t("group_expert_anti_loop"))

        self.rep_penalty_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1.0, 1.5, 0.05)
        self.rep_penalty_scale.set_value(self.config.get("repetition_penalty", 1.1))
        self.rep_penalty_scale.set_digits(2)
        self.rep_penalty_scale.set_size_request(160, -1)
        self.rep_penalty_scale.connect("value-changed", self.auto_save)
        list_anti_loop.add(self._create_control_row(self.i18n.t("lbl_repetition_penalty"), self.rep_penalty_scale, self.i18n.t("desc_repetition_penalty")))

        self.no_repeat_ngram_spin = Gtk.SpinButton.new_with_range(0, 5, 1)
        self.no_repeat_ngram_spin.set_value(self.config.get("no_repeat_ngram_size", 0))
        self.no_repeat_ngram_spin.connect("value-changed", self.auto_save)
        list_anti_loop.add(self._create_control_row(self.i18n.t("lbl_no_repeat_ngram_size"), self.no_repeat_ngram_spin, self.i18n.t("desc_no_repeat_ngram_size")))

        self.hallucination_silence_spin = Gtk.SpinButton.new_with_range(0.0, 5.0, 0.5)
        self.hallucination_silence_spin.set_value(self.config.get("hallucination_silence_threshold", 2.0))
        self.hallucination_silence_spin.set_digits(1)
        self.hallucination_silence_spin.connect("value-changed", self.auto_save)
        list_anti_loop.add(self._create_control_row(self.i18n.t("lbl_hallucination_silence_threshold"), self.hallucination_silence_spin, self.i18n.t("desc_hallucination_silence_threshold")))

        expert_vbox.pack_start(card_anti_loop, False, False, 0)

        # Sub-Card 3: Fine-Tuned Decoding
        card_decoding, list_decoding = self._create_card(self.i18n.t("group_expert_decoding"))

        self.beam_patience_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.5, 2.0, 0.1)
        self.beam_patience_scale.set_value(self.config.get("beam_patience", 1.0))
        self.beam_patience_scale.set_digits(1)
        self.beam_patience_scale.set_size_request(160, -1)
        self.beam_patience_scale.connect("value-changed", self.auto_save)
        list_decoding.add(self._create_control_row(self.i18n.t("lbl_beam_patience"), self.beam_patience_scale, self.i18n.t("desc_beam_patience")))

        self.length_penalty_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.2, 2.0, 0.1)
        self.length_penalty_scale.set_value(self.config.get("length_penalty", 1.0))
        self.length_penalty_scale.set_digits(1)
        self.length_penalty_scale.set_size_request(160, -1)
        self.length_penalty_scale.connect("value-changed", self.auto_save)
        list_decoding.add(self._create_control_row(self.i18n.t("lbl_length_penalty"), self.length_penalty_scale, self.i18n.t("desc_length_penalty")))

        self.condition_on_previous_switch = Gtk.Switch()
        self.condition_on_previous_switch.set_active(self.config.get("condition_on_previous_text", True))
        self.condition_on_previous_switch.connect("notify::active", self.auto_save)
        list_decoding.add(self._create_switch_row(self.i18n.t("lbl_condition_on_previous_text"), self.condition_on_previous_switch, self.i18n.t("desc_condition_on_previous_text")))

        expert_vbox.pack_start(card_decoding, False, False, 0)

        # Sub-Card 4: Detailed VAD Parameters
        self.card_vad_expert, list_vad_expert = self._create_card(self.i18n.t("group_expert_vad"))

        self.vad_threshold_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.1, 0.9, 0.05)
        self.vad_threshold_scale.set_value(self.config.get("vad_threshold", 0.5))
        self.vad_threshold_scale.set_digits(2)
        self.vad_threshold_scale.set_size_request(160, -1)
        self.vad_threshold_scale.connect("value-changed", self.auto_save)
        list_vad_expert.add(self._create_control_row(self.i18n.t("lbl_vad_threshold"), self.vad_threshold_scale, self.i18n.t("desc_vad_threshold")))

        self.vad_speech_pad_spin = Gtk.SpinButton.new_with_range(100, 1000, 50)
        self.vad_speech_pad_spin.set_value(self.config.get("vad_speech_pad_ms", 400))
        self.vad_speech_pad_spin.connect("value-changed", self.auto_save)
        list_vad_expert.add(self._create_control_row(self.i18n.t("lbl_vad_speech_pad"), self.vad_speech_pad_spin, self.i18n.t("desc_vad_speech_pad")))

        self.vad_min_silence_spin = Gtk.SpinButton.new_with_range(500, 3000, 100)
        self.vad_min_silence_spin.set_value(self.config.get("vad_min_silence_duration_ms", 2000))
        self.vad_min_silence_spin.connect("value-changed", self.auto_save)
        list_vad_expert.add(self._create_control_row(self.i18n.t("lbl_vad_min_silence"), self.vad_min_silence_spin, self.i18n.t("desc_vad_min_silence")))

        self.card_vad_expert.set_sensitive(self.vad_switch.get_active())
        expert_vbox.pack_start(self.card_vad_expert, False, False, 0)

        self.expert_expander.add(expert_vbox)
        adv_box.pack_start(self.expert_expander, False, False, 0)

        # ---------------------------------------------------------
        # Tab 5: Gestor de Modelos (Model Manager)
        # ---------------------------------------------------------
        models_scroll = Gtk.ScrolledWindow()
        models_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        models_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        models_box.get_style_context().add_class("page-container")
        models_scroll.add(models_box)
        self.stack.add_titled(models_scroll, "models", self.i18n.t("tab_models"))

        card_models, list_models = self._create_card(self.i18n.t("tab_models"))
        self.models_listbox = list_models
        models_box.pack_start(card_models, True, True, 0)

        self.refresh_models_list()

        # ---------------------------------------------------------
        # Tab 6: Shortcuts & Integrations
        # ---------------------------------------------------------
        shortcuts_scroll = Gtk.ScrolledWindow()
        shortcuts_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        shortcuts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        shortcuts_box.get_style_context().add_class("page-container")
        shortcuts_scroll.add(shortcuts_box)
        self.stack.add_titled(shortcuts_scroll, "shortcuts", self.i18n.t("tab_shortcuts"))

        # Card 1: CLI Commands & Terminal Actions
        card_cli, list_cli = self._create_card(self.i18n.t("group_cli_commands"))
        cli_commands = [
            ("opendictate --toggle-record-send", self.i18n.t("cli_desc_toggle_record_send")),
            ("opendictate --record", self.i18n.t("cli_desc_record")),
            ("opendictate --pause", self.i18n.t("cli_desc_pause")),
            ("opendictate --cancel", self.i18n.t("cli_desc_cancel")),
            ("opendictate --send", self.i18n.t("cli_desc_send")),
            ("opendictate --toggle-ai", self.i18n.t("cli_desc_toggle_ai")),
            ("opendictate --toggle-autosend", self.i18n.t("cli_desc_toggle_autosend")),
            ("opendictate --toggle-bubble", self.i18n.t("cli_desc_toggle_bubble")),
        ]
        for cmd, desc in cli_commands:
            list_cli.add(self._create_cli_command_row(cmd, desc))
        shortcuts_box.pack_start(card_cli, False, False, 0)

        # Card 2: OpenDeck Integration
        card_opendeck, list_opendeck = self._create_card(self.i18n.t("group_opendeck_integration"))
        self.opendeck_row = Gtk.ListBoxRow()
        self.opendeck_row.get_style_context().add_class("preference-row")
        opendeck_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        opendeck_hbox.set_margin_top(6)
        opendeck_hbox.set_margin_bottom(6)
        opendeck_hbox.set_margin_left(8)
        opendeck_hbox.set_margin_right(8)

        self.opendeck_status_lbl = Gtk.Label(xalign=0)
        self.opendeck_status_lbl.get_style_context().add_class("row-title")
        opendeck_hbox.pack_start(self.opendeck_status_lbl, True, True, 0)

        self.opendeck_install_btn = Gtk.Button()
        self.opendeck_install_btn.connect("clicked", self._on_install_opendeck_clicked)
        opendeck_hbox.pack_end(self.opendeck_install_btn, False, False, 0)
        self.opendeck_row.add(opendeck_hbox)
        list_opendeck.add(self.opendeck_row)
        shortcuts_box.pack_start(card_opendeck, False, False, 0)

        # Card 3: GNOME Shell Top Bar Integration
        card_gnome, list_gnome = self._create_card(self.i18n.t("group_gnome_integration"))
        self.gnome_row = Gtk.ListBoxRow()
        self.gnome_row.get_style_context().add_class("preference-row")
        gnome_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        gnome_hbox.set_margin_top(6)
        gnome_hbox.set_margin_bottom(6)
        gnome_hbox.set_margin_left(8)
        gnome_hbox.set_margin_right(8)

        self.gnome_status_lbl = Gtk.Label(xalign=0)
        self.gnome_status_lbl.get_style_context().add_class("row-title")
        gnome_hbox.pack_start(self.gnome_status_lbl, True, True, 0)

        self.gnome_toggle_btn = Gtk.Button()
        self.gnome_toggle_btn.connect("clicked", self._on_toggle_gnome_ext_clicked)
        gnome_hbox.pack_end(self.gnome_toggle_btn, False, False, 0)
        self.gnome_row.add(gnome_hbox)
        list_gnome.add(self.gnome_row)
        shortcuts_box.pack_start(card_gnome, False, False, 0)

        # Card 4: Keyboard Shortcuts Guide
        card_guide, list_guide = self._create_card(self.i18n.t("group_shortcuts_guide"))
        list_guide.add(self._create_guide_row(self.i18n.t("guide_gnome_title"), self.i18n.t("guide_gnome_desc")))
        list_guide.add(self._create_guide_row(self.i18n.t("guide_kde_title"), self.i18n.t("guide_kde_desc")))
        shortcuts_box.pack_start(card_guide, False, False, 0)

        self._refresh_integrations_status()

        self.show_all()


    def on_manage_apps_clicked(self, widget):
        dialog = AppProfilesDialog(self, self.config, self.db_path, self.i18n, self.auto_save)
        dialog.run()
        dialog.destroy()

    def _apply_css(self) -> None:
        """Inject dark theme styles into GTK StyleContext."""
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(SETTINGS_CSS)
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _create_card(self, title: str) -> Tuple[Gtk.Box, Gtk.ListBox]:
        """Create structured card frame with optional header."""
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        if title:
            escaped_title = GLib.markup_escape_text(title.upper())
            lbl = Gtk.Label(xalign=0)
            lbl.set_markup(f"<span size='small' weight='bold' foreground='#888888'>{escaped_title}</span>")
            lbl.get_style_context().add_class("section-title")
            container.pack_start(lbl, False, False, 2)

        frame = Gtk.Frame()
        frame.get_style_context().add_class("card-frame")
        frame.set_shadow_type(Gtk.ShadowType.NONE)

        listbox = Gtk.ListBox()
        listbox.get_style_context().add_class("card-list")
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        frame.add(listbox)
        container.pack_start(frame, False, False, 0)
        return container, listbox

    def _create_switch_row(self, title: str, switch: Gtk.Switch, subtitle: Optional[str] = None) -> Gtk.ListBoxRow:
        """Create standard preference row containing left-aligned label and right-aligned switch."""
        row = Gtk.ListBoxRow()
        row.get_style_context().add_class("preference-row")
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hbox.set_margin_top(4)
        hbox.set_margin_bottom(4)
        hbox.set_margin_left(8)
        hbox.set_margin_right(8)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_lbl = Gtk.Label(label=title, xalign=0)
        title_lbl.get_style_context().add_class("row-title")
        vbox.pack_start(title_lbl, False, False, 0)
        if subtitle:
            sub_lbl = Gtk.Label(label=subtitle, xalign=0)
            sub_lbl.get_style_context().add_class("row-subtitle")
            vbox.pack_start(sub_lbl, False, False, 0)

        hbox.pack_start(vbox, True, True, 0)
        switch.set_valign(Gtk.Align.CENTER)
        switch.set_halign(Gtk.Align.END)
        hbox.pack_end(switch, False, False, 0)
        row.add(hbox)
        return row

    def _create_control_row(self, title: str, control: Gtk.Widget, subtitle: Optional[str] = None) -> Gtk.ListBoxRow:
        """Create standard preference row containing left-aligned label and right-aligned control widget."""
        row = Gtk.ListBoxRow()
        row.get_style_context().add_class("preference-row")
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hbox.set_margin_top(4)
        hbox.set_margin_bottom(4)
        hbox.set_margin_left(8)
        hbox.set_margin_right(8)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_lbl = Gtk.Label(label=title, xalign=0)
        title_lbl.get_style_context().add_class("row-title")
        vbox.pack_start(title_lbl, False, False, 0)
        if subtitle:
            sub_lbl = Gtk.Label(label=subtitle, xalign=0)
            sub_lbl.get_style_context().add_class("row-subtitle")
            vbox.pack_start(sub_lbl, False, False, 0)

        hbox.pack_start(vbox, True, True, 0)
        control.set_valign(Gtk.Align.CENTER)
        control.set_halign(Gtk.Align.END)
        hbox.pack_end(control, False, False, 0)
        row.add(hbox)
        return row

    def _on_realtime_switch_changed(self, switch: Gtk.Switch, *args) -> None:
        """Update sensitivity of chunking parameters and trigger auto-save."""
        if hasattr(self, 'chunk_options_box'):
            self.chunk_options_box.set_sensitive(switch.get_active())
        self.auto_save()

    def _on_vad_switch_changed(self, switch: Gtk.Switch, *args) -> None:
        """Update sensitivity of expert VAD parameters card and trigger auto-save."""
        if hasattr(self, 'card_vad_expert'):
            self.card_vad_expert.set_sensitive(switch.get_active())
        self.auto_save()

    def _populate_compute_types(self, device: str) -> None:
        """Populate compute type combo options based on target device support."""
        if not hasattr(self, 'compute_combo'):
            return
        active_id = self.compute_combo.get_active_id() or self.config.get("whisper_compute_type", "default")
        self.compute_combo.remove_all()
        types = get_supported_compute_types(device)
        for ct in types:
            self.compute_combo.append(ct, ct)
        if active_id in types:
            self.compute_combo.set_active_id(active_id)
        else:
            self.compute_combo.set_active_id("default")

    def _on_expert_device_changed(self, combo: Gtk.ComboBoxText) -> None:
        """Handle execution device change and refresh supported compute types."""
        dev = combo.get_active_id() or "auto"
        self._populate_compute_types(dev)
        self.auto_save()

    def on_delete_event(self, widget: Gtk.Widget, event: Any) -> bool:
        self.hide()
        return True

    def refresh_models_list(self) -> None:
        for child in self.models_listbox.get_children():
            self.models_listbox.remove(child)

        models = [
            "tiny", "tiny.en", "base", "base.en", "small", "small.en",
            "medium", "medium.en", "large-v1", "large-v2", "large-v3", "large"
        ]
        active_model = self.config.get("whisper_model_size", "medium")

        for m in models:
            row = Gtk.ListBoxRow()
            row.get_style_context().add_class("preference-row")
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            hbox.set_margin_top(4)
            hbox.set_margin_bottom(4)
            hbox.set_margin_left(8)
            hbox.set_margin_right(8)
            row.add(hbox)

            # Name
            name_lbl = Gtk.Label(label=m, xalign=0)
            name_lbl.get_style_context().add_class("row-title")
            if m == active_model:
                escaped_m = GLib.markup_escape_text(m)
                escaped_tag = GLib.markup_escape_text(self.i18n.t('active_model'))
                name_lbl.set_markup(f"<b>{escaped_m}</b> <span foreground='#3584e4'>{escaped_tag}</span>")
            hbox.pack_start(name_lbl, True, True, 0)

            # Status
            hf_path = os.path.expanduser(f"~/.cache/huggingface/hub/models--Systran--faster-whisper-{m}")
            downloaded = os.path.exists(hf_path)
            status_str = self.i18n.t("model_downloaded") if downloaded else self.i18n.t("model_not_downloaded")
            status_lbl = Gtk.Label(label=status_str)
            status_lbl.get_style_context().add_class("badge-downloaded" if downloaded else "badge-not-downloaded")
            hbox.pack_start(status_lbl, False, False, 10)

            # Actions Box
            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

            # Uninstall / Delete Button
            if downloaded:
                btn_del = Gtk.Button()
                del_icon = Gtk.Image.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON)
                btn_del.set_image(del_icon)
                btn_del.set_tooltip_text(self.i18n.t("btn_delete_model"))
                btn_del.connect("clicked", self.on_delete_model_clicked, m, hf_path)
                btn_box.pack_start(btn_del, False, False, 0)

            # Activate Button
            btn_act = Gtk.Button(label=self.i18n.t("btn_activate"))
            if m == active_model:
                btn_act.set_sensitive(False)
            btn_act.connect("clicked", self.on_activate_model_clicked, m)
            btn_box.pack_start(btn_act, False, False, 0)

            hbox.pack_end(btn_box, False, False, 0)
            self.models_listbox.add(row)

        self.models_listbox.show_all()

    def on_delete_model_clicked(self, widget: Gtk.Button, model_name: str, hf_path: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=self.i18n.t("confirm_delete_model_title")
        )
        dialog.format_secondary_text(self.i18n.t("confirm_delete_model_msg", model_name))
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            try:
                if os.path.exists(hf_path):
                    shutil.rmtree(hf_path)
                self.refresh_models_list()
            except Exception as e:
                self.show_message(self.i18n.t("error", ""), str(e))

    def on_activate_model_clicked(self, widget: Gtk.Widget, model_name: str) -> None:
        self.config["whisper_model_size"] = model_name
        self.auto_save()
        self.refresh_models_list()

    def on_indicator_mode_changed(self, combo: Gtk.ComboBoxText) -> None:
        if self._updating_ui:
            return
        mode = combo.get_active_id() or "auto"
        from core.hardware import detect_desktop_environment
        _, is_gnome = detect_desktop_environment()

        if mode == "gnome_ext" and not is_gnome:
            self.show_message(self.i18n.t("error", ""), self.i18n.t("indicator_gnome_unavailable"))
            self.indicator_combo.set_active_id("tray")
            mode = "tray"

        self.config["indicator_mode"] = mode
        uuid = "com.kirulab.opendictate@kirulab.com"

        if mode == "gnome_ext":
            self.config["use_gnome_ext"] = True
            self.config["use_appindicator"] = False
            subprocess.Popen(["gnome-extensions", "enable", uuid])
        elif mode == "tray":
            self.config["use_gnome_ext"] = False
            self.config["use_appindicator"] = True
            subprocess.Popen(["gnome-extensions", "disable", uuid])
        elif mode == "none":
            self.config["use_gnome_ext"] = False
            self.config["use_appindicator"] = False
            subprocess.Popen(["gnome-extensions", "disable", uuid])
        else:  # "auto"
            self.config["use_gnome_ext"] = is_gnome
            self.config["use_appindicator"] = not is_gnome
            if is_gnome:
                subprocess.Popen(["gnome-extensions", "enable", uuid])
            else:
                subprocess.Popen(["gnome-extensions", "disable", uuid])

        self.auto_save()

    def on_launch_wizard_clicked(self, widget: Gtk.Button) -> None:
        try:
            from ui.wizard import FirstRunWizard
            from core.config import ConfigManager
            config_mgr = ConfigManager()
            wizard = FirstRunWizard(
                config_mgr,
                on_finish=lambda cfg: (self.update_ui_from_config(cfg), self.daemon_ref.on_config_saved(cfg) if self.daemon_ref else None)
            )
            wizard.present()
        except Exception as e:
            self.show_message(self.i18n.t("error", ""), str(e))

    def load_config(self) -> Dict[str, Any]:
        if self.daemon_ref and hasattr(self.daemon_ref, 'config'):
            return self.daemon_ref.config.copy()
        if hasattr(self, 'config_manager'):
            return self.config_manager.load_config()
        return {}

    def update_ui_from_config(self, new_config: Dict[str, Any]) -> None:
        self._updating_ui = True
        self.config = new_config

        self.auto_send_switch.set_active(self.config.get("auto_send", False))
        self.ai_enabled_switch.set_active(self.config.get("ai_enabled", False))
        self.hide_bubble_switch.set_active(self.config.get("hide_bubble", False))
        self.auto_pause_switch.set_active(self.config.get("auto_pause_media", True))
        if hasattr(self, 'bubble_mode_combo'):
            self.bubble_mode_combo.set_active_id(self.config.get("bubble_mode", "auto"))
            self.bubble_mode_combo.set_sensitive(not self.config.get("hide_bubble", False))
        if hasattr(self, 'notifications_switch'):
            self.notifications_switch.set_active(self.config.get("show_notifications", True))
        if hasattr(self, 'restore_focus_switch'):
            self.restore_focus_switch.set_active(self.config.get("restore_window_focus", False))
        if hasattr(self, 'check_updates_switch'):
            self.check_updates_switch.set_active(self.config.get("check_updates", False))
        if hasattr(self, 'update_freq_combo'):
            self.update_freq_combo.set_active_id(self.config.get("update_frequency", "monthly"))
            self.update_freq_combo.set_sensitive(self.config.get("check_updates", False))

        self.api_key_entry.set_text(self.config.get("api_key", ""))
        self.model_entry.set_text(self.config.get("model", "gemma-4-26b-a4b-it"))

        if hasattr(self, 'llm_timeout_spin'):
            self.llm_timeout_spin.set_value(self.config.get("llm_timeout", 120))
            self.llm_temp_scale.set_value(self.config.get("llm_temperature", 0.7))
            self.llm_thinking_switch.set_active(self.config.get("llm_thinking", False))

        if hasattr(self, 'realtime_switch'):
            is_rt = self.config.get("realtime_mode", True)
            self.realtime_switch.set_active(is_rt)
            if hasattr(self, 'chunk_options_box'):
                self.chunk_options_box.set_sensitive(is_rt)

        if hasattr(self, 'vad_switch'):
            if hasattr(self, 'chunk_silence_spin'):
                self.chunk_silence_spin.set_value(self.config.get("chunk_silence_duration", 0.6))
                self.chunk_max_spin.set_value(self.config.get("chunk_max_duration", 30.0))
                self.chunk_fallback_silence_spin.set_value(self.config.get("chunk_fallback_silence_duration", 0.4))
                self.chunk_min_spin.set_value(self.config.get("chunk_min_duration", 3.0))
            self.vad_switch.set_active(self.config.get("vad_filter", False))
            self.lang_combo.set_active_id(self.config.get("language", "auto"))
            self.ui_lang_combo.set_active_id(self.config.get("ui_language", "en"))
            self.beam_scale.set_value(self.config.get("beam_size", 5))
            self.temp_scale.set_value(self.config.get("temperature", 0.0))

        if hasattr(self, 'device_combo'):
            cuda_ready = is_cuda_runtime_ready()
            dev = self.config.get("whisper_device", "auto")
            if dev == "cuda" and not cuda_ready:
                dev = "auto"
                self.config["whisper_device"] = "auto"
            self.device_combo.set_active_id(dev)
            self._populate_compute_types(dev)
            self.compute_combo.set_active_id(self.config.get("whisper_compute_type", "default"))
            self.cpu_threads_spin.set_value(self.config.get("whisper_cpu_threads", 0))
            self.rep_penalty_scale.set_value(self.config.get("repetition_penalty", 1.1))
            self.no_repeat_ngram_spin.set_value(self.config.get("no_repeat_ngram_size", 0))
            self.hallucination_silence_spin.set_value(self.config.get("hallucination_silence_threshold", 2.0))
            self.beam_patience_scale.set_value(self.config.get("beam_patience", 1.0))
            self.length_penalty_scale.set_value(self.config.get("length_penalty", 1.0))
            self.condition_on_previous_switch.set_active(self.config.get("condition_on_previous_text", True))
            self.vad_threshold_scale.set_value(self.config.get("vad_threshold", 0.5))
            self.vad_speech_pad_spin.set_value(self.config.get("vad_speech_pad_ms", 400))
            self.vad_min_silence_spin.set_value(self.config.get("vad_min_silence_duration_ms", 2000))
            if hasattr(self, 'card_vad_expert'):
                self.card_vad_expert.set_sensitive(self.config.get("vad_filter", False))

        if hasattr(self, 'indicator_combo'):
            self.indicator_combo.set_active_id(self.config.get("indicator_mode", "auto"))

        self._refresh_integrations_status()
        self._updating_ui = False

    def on_ui_language_changed(self, combo: Gtk.ComboBoxText, *args) -> None:
        if self._updating_ui:
            return
        new_lang = combo.get_active_id() or "en"
        if new_lang == self.config.get("ui_language"):
            return

        self._updating_ui = True
        self.config["ui_language"] = new_lang
        self.i18n = get_translator(new_lang)
        self.config_manager.save_config(self.config)

        if self.on_config_saved:
            try:
                self.on_config_saved(self.config)
            except Exception as e:
                logging.error(f"Error in on_config_saved: {e}")
        else:
            self._notify_daemon_reload()

        self._updating_ui = False
        self._rebuild_ui()

    def _rebuild_ui(self) -> None:
        active_tab = "general"
        if hasattr(self, 'stack') and self.stack:
            active_tab = self.stack.get_visible_child_name() or "general"

        for child in self.get_children():
            self.remove(child)

        self._build_ui()
        self.set_title(self.i18n.t("settings_title"))
        if hasattr(self, 'stack') and self.stack:
            self.stack.set_visible_child_name(active_tab)
        self.show_all()

    def _notify_daemon_reload(self) -> None:
        try:
            from core.ipc import SOCKET_PATH
            import socket
            if os.path.exists(SOCKET_PATH):
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(0.5)
                s.connect(SOCKET_PATH)
                s.sendall(b"reload-config\n")
                s.close()
        except Exception as e:
            logging.debug(f"Could not notify daemon of config change: {e}")

        try:
            state_file = "/tmp/opendictate_state.json"
            state_data = {}
            if os.path.exists(state_file):
                with open(state_file, "r") as f:
                    state_data = json.load(f)
            state_data["ui_language"] = self.config.get("ui_language", "en")
            tmp_path = "/tmp/opendictate_state.json.tmp"
            with open(tmp_path, "w") as f:
                json.dump(state_data, f)
            os.replace(tmp_path, state_file)
        except Exception as e:
            logging.debug(f"Could not sync state file directly: {e}")

    def _on_hide_bubble_changed(self, switch, gparam):
        self.bubble_mode_combo.set_sensitive(not switch.get_active())
        self.auto_save()

    def _on_check_updates_changed(self, switch, gparam):
        self.update_freq_combo.set_sensitive(switch.get_active())
        self.auto_save()

    def _on_manual_check_updates(self, btn):
        from core.updater import check_for_updates
        window = self.get_window()
        if window:
            window.set_cursor(Gdk.Cursor.new_from_name(window.get_display(), "wait"))
        
        def _reset_cursor():
            if window:
                window.set_cursor(None)
                
        check_for_updates(self.config, self.config_manager, force=True)
        GLib.timeout_add(2000, _reset_cursor)

    def auto_save(self, *args) -> None:
        if self._updating_ui:
            return

        self.config["auto_send"] = self.auto_send_switch.get_active()
        self.config["ai_enabled"] = self.ai_enabled_switch.get_active()
        self.config["hide_bubble"] = self.hide_bubble_switch.get_active()
        self.config["auto_pause_media"] = self.auto_pause_switch.get_active()
        if hasattr(self, 'bubble_mode_combo'):
            self.config["bubble_mode"] = self.bubble_mode_combo.get_active_id() or "auto"
        if hasattr(self, 'check_updates_switch'):
            self.config["check_updates"] = self.check_updates_switch.get_active()
        if hasattr(self, 'update_freq_combo'):
            self.config["update_frequency"] = self.update_freq_combo.get_active_id() or "monthly"
        if hasattr(self, 'indicator_combo'):
            self.config["indicator_mode"] = self.indicator_combo.get_active_id() or "auto"
        if hasattr(self, 'notifications_switch'):
            self.config["show_notifications"] = self.notifications_switch.get_active()
        if hasattr(self, 'restore_focus_switch'):
            self.config["restore_window_focus"] = self.restore_focus_switch.get_active()

        if hasattr(self, 'realtime_switch'):
            self.config["realtime_mode"] = self.realtime_switch.get_active()

        # Handle autostart desktop file
        autostart_dir = os.path.expanduser("~/.config/autostart")
        autostart_path = os.path.join(autostart_dir, "opendictate.desktop")
        if self.autostart_switch.get_active():
            os.makedirs(autostart_dir, exist_ok=True)
            install_dir = os.path.expanduser("~/.local/share/opendictate")
            desktop_content = f"""[Desktop Entry]
Type=Application
Name=OpenDictate
Comment=Background daemon for global voice dictation using faster-whisper
Exec={install_dir}/.venv/bin/python {install_dir}/opendictate-daemon.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Icon=audio-input-microphone
"""
            with open(autostart_path, "w") as f:
                f.write(desktop_content)
        else:
            if os.path.exists(autostart_path):
                os.remove(autostart_path)

        # Save Model / AI Settings
        self.config["api_key"] = self.api_key_entry.get_text().strip()
        self.config["model"] = self.model_entry.get_text().strip()
        if hasattr(self, 'llm_timeout_spin'):
            self.config["llm_timeout"] = int(self.llm_timeout_spin.get_value())
            self.config["llm_temperature"] = float(self.llm_temp_scale.get_value())
            self.config["llm_thinking"] = self.llm_thinking_switch.get_active()

        # Save Engine & Advanced Settings
        if hasattr(self, 'vad_switch'):
            if hasattr(self, 'chunk_silence_spin'):
                self.config["chunk_silence_duration"] = float(self.chunk_silence_spin.get_value())
                self.config["chunk_max_duration"] = float(self.chunk_max_spin.get_value())
                self.config["chunk_fallback_silence_duration"] = float(self.chunk_fallback_silence_spin.get_value())
                self.config["chunk_min_duration"] = float(self.chunk_min_spin.get_value())
            self.config["vad_filter"] = self.vad_switch.get_active()
            self.config["language"] = self.lang_combo.get_active_id()
            self.config["ui_language"] = self.ui_lang_combo.get_active_id()
            self.config["beam_size"] = int(self.beam_scale.get_value())
            self.config["temperature"] = float(self.temp_scale.get_value())

        if hasattr(self, 'device_combo'):
            dev = self.device_combo.get_active_id() or "auto"
            if dev == "cuda" and not is_cuda_runtime_ready():
                dev = "auto"
            self.config["whisper_device"] = dev
            self.config["whisper_compute_type"] = self.compute_combo.get_active_id() or "default"
            self.config["whisper_cpu_threads"] = int(self.cpu_threads_spin.get_value())
            self.config["repetition_penalty"] = float(self.rep_penalty_scale.get_value())
            self.config["no_repeat_ngram_size"] = int(self.no_repeat_ngram_spin.get_value())
            self.config["hallucination_silence_threshold"] = float(self.hallucination_silence_spin.get_value())
            self.config["beam_patience"] = float(self.beam_patience_scale.get_value())
            self.config["length_penalty"] = float(self.length_penalty_scale.get_value())
            self.config["condition_on_previous_text"] = self.condition_on_previous_switch.get_active()
            self.config["vad_threshold"] = float(self.vad_threshold_scale.get_value())
            self.config["vad_speech_pad_ms"] = int(self.vad_speech_pad_spin.get_value())
            self.config["vad_min_silence_duration_ms"] = int(self.vad_min_silence_spin.get_value())

        buf = self.base_prompt_view.get_buffer()
        start, end = buf.get_bounds()
        self.config["base_system_prompt"] = buf.get_text(start, end, True).strip()

        if self.on_config_saved:
            try:
                self.on_config_saved(self.config)
            except Exception as e:
                logging.error(f"Error in on_config_saved: {e}")
        elif hasattr(self, 'config_manager'):
            self.config_manager.save_config(self.config)
            self._notify_daemon_reload()







    def show_message(self, title: str, message: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=title
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def _create_cli_command_row(self, cmd: str, desc: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.get_style_context().add_class("preference-row")
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hbox.set_margin_top(6)
        hbox.set_margin_bottom(6)
        hbox.set_margin_left(8)
        hbox.set_margin_right(8)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        cmd_lbl = Gtk.Label(xalign=0)
        escaped_cmd = GLib.markup_escape_text(cmd)
        cmd_lbl.set_markup(f"<span font_family='monospace' weight='bold' foreground='#78aeed'>{escaped_cmd}</span>")
        vbox.pack_start(cmd_lbl, False, False, 0)

        desc_lbl = Gtk.Label(label=desc, xalign=0)
        desc_lbl.get_style_context().add_class("row-subtitle")
        vbox.pack_start(desc_lbl, False, False, 0)

        hbox.pack_start(vbox, True, True, 0)

        copy_btn = Gtk.Button(label=self.i18n.t("btn_copy"))
        copy_btn.set_valign(Gtk.Align.CENTER)
        copy_btn.connect("clicked", self._on_copy_cli_clicked, cmd)
        hbox.pack_end(copy_btn, False, False, 0)

        row.add(hbox)
        return row

    def _on_copy_cli_clicked(self, btn: Gtk.Button, cmd: str) -> None:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(cmd, -1)
        original_label = btn.get_label()
        btn.set_label(self.i18n.t("copied_toast"))
        GLib.timeout_add(1500, lambda: btn.set_label(original_label))

    def _create_guide_row(self, title: str, desc: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.get_style_context().add_class("preference-row")
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_margin_top(6)
        vbox.set_margin_bottom(6)
        vbox.set_margin_left(8)
        vbox.set_margin_right(8)

        title_lbl = Gtk.Label(label=title, xalign=0)
        title_lbl.get_style_context().add_class("row-title")
        vbox.pack_start(title_lbl, False, False, 0)

        desc_lbl = Gtk.Label(label=desc, xalign=0)
        desc_lbl.set_line_wrap(True)
        desc_lbl.get_style_context().add_class("row-subtitle")
        vbox.pack_start(desc_lbl, False, False, 0)

        row.add(vbox)
        return row

    def _refresh_integrations_status(self) -> None:
        if not hasattr(self, 'opendeck_status_lbl') or not hasattr(self, 'gnome_status_lbl'):
            return

        # OpenDeck status
        opendeck_plugin_path = os.path.expanduser("~/.config/opendeck/plugins/com.kirulab.opendictate.sdplugin")
        if os.path.exists(opendeck_plugin_path):
            self.opendeck_status_lbl.set_text(self.i18n.t("opendeck_status_installed"))
            self.opendeck_install_btn.set_label(self.i18n.t("btn_reinstall_opendeck"))
        else:
            self.opendeck_status_lbl.set_text(self.i18n.t("opendeck_status_missing"))
            self.opendeck_install_btn.set_label(self.i18n.t("btn_install_opendeck"))

        # GNOME extension status
        uuid = "com.kirulab.opendictate@kirulab.com"
        is_enabled = False
        try:
            res = subprocess.run(["gnome-extensions", "show", uuid], capture_output=True, text=True, timeout=0.8)
            if res.returncode == 0 and any(k in res.stdout for k in ["State: ENABLED", "State: 1", "ENABLED", "ACTIVE", "Activado: Sí"]):
                is_enabled = True
        except Exception:
            pass

        if is_enabled:
            self.gnome_status_lbl.set_text(self.i18n.t("gnome_ext_status_enabled"))
            self.gnome_toggle_btn.set_label(self.i18n.t("btn_disable_gnome_ext"))
        else:
            self.gnome_status_lbl.set_text(self.i18n.t("gnome_ext_status_disabled"))
            self.gnome_toggle_btn.set_label(self.i18n.t("btn_enable_gnome_ext"))

    def _on_install_opendeck_clicked(self, widget: Gtk.Button) -> None:
        opendeck_plugins_dir = os.path.expanduser("~/.config/opendeck/plugins/")
        plugin_name = "com.kirulab.opendictate.sdplugin"
        target_dir = os.path.join(opendeck_plugins_dir, plugin_name)
        source_dir = os.path.join(os.path.expanduser("~/.local/share/opendictate"), "plugins", plugin_name)
        if not os.path.exists(source_dir):
            source_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins", plugin_name)

        try:
            os.makedirs(opendeck_plugins_dir, exist_ok=True)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            if os.path.exists(source_dir):
                shutil.copytree(source_dir, target_dir)
                self.show_message(self.i18n.t("opendeck"), self.i18n.t("opendeck_installed_success"))
            else:
                self.show_message(self.i18n.t("error", ""), self.i18n.t("error_plugin_not_found"))
        except Exception as e:
            self.show_message(self.i18n.t("error", ""), str(e))
        self._refresh_integrations_status()

    def _on_toggle_gnome_ext_clicked(self, widget: Gtk.Button) -> None:
        uuid = "com.kirulab.opendictate@kirulab.com"
        btn_label = widget.get_label()
        if btn_label == self.i18n.t("btn_enable_gnome_ext"):
            subprocess.run(["gnome-extensions", "enable", uuid])
        else:
            subprocess.run(["gnome-extensions", "disable", uuid])
        GLib.timeout_add(400, self._refresh_integrations_status)


if __name__ == "__main__":
    import logging
    from core.config import CONFIG_PATH
    logging.basicConfig(level=logging.INFO)
    db = os.path.expanduser("~/.local/share/opendictate/opendictate.db")
    win = ConfigWindow(db, CONFIG_PATH)
    win.connect("destroy", Gtk.main_quit)
    Gtk.main()



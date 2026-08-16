"""
GTK Configuration Window UI module for OpenDictate.

Renders multi-tab settings window for General settings, Application Profiles,
AI Model settings, Whisper Model Manager, and Advanced Desktop Integration.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import sqlite3
import json
import os
from typing import Dict, Any, Optional, Callable
from i18n import get_translator


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
        
        self.config = self.load_config()
        self.i18n = get_translator(self.config.get("ui_language", "en"))
        
        self._updating_ui = False

        super().__init__(title=self.i18n.t("settings_title"))
        self.set_default_size(650, 450)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("delete-event", self.on_delete_event)
        
        notebook = Gtk.Notebook()
        self.add(notebook)
        
        # Tab 1: General
        general_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        general_box.set_border_width(15)
        notebook.append_page(general_box, Gtk.Label(label=self.i18n.t("tab_general")))
        
        switch_box2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_auto_send = Gtk.Label(label=self.i18n.t("lbl_autosend"))
        self.auto_send_switch = Gtk.Switch()
        self.auto_send_switch.set_active(self.config.get("auto_send", False))
        self.auto_send_switch.connect("notify::active", self.auto_save)
        switch_box2.pack_start(lbl_auto_send, False, False, 0)
        switch_box2.pack_start(self.auto_send_switch, False, False, 0)
        general_box.pack_start(switch_box2, False, False, 0)

        switch_box3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_ai_enabled = Gtk.Label(label=self.i18n.t("lbl_ai_enabled"))
        self.ai_enabled_switch = Gtk.Switch()
        self.ai_enabled_switch.set_active(self.config.get("ai_enabled", False))
        self.ai_enabled_switch.connect("notify::active", self.auto_save)
        switch_box3.pack_start(lbl_ai_enabled, False, False, 0)
        switch_box3.pack_start(self.ai_enabled_switch, False, False, 0)
        general_box.pack_start(switch_box3, False, False, 0)
        
        switch_box4 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_hide_bubble = Gtk.Label(label=self.i18n.t("lbl_hide_bubble"))
        self.hide_bubble_switch = Gtk.Switch()
        self.hide_bubble_switch.set_active(self.config.get("hide_bubble", False))
        self.hide_bubble_switch.connect("notify::active", self.auto_save)
        switch_box4.pack_start(lbl_hide_bubble, False, False, 0)
        switch_box4.pack_start(self.hide_bubble_switch, False, False, 0)
        general_box.pack_start(switch_box4, False, False, 0)

        switch_box5 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_auto_pause = Gtk.Label(label=self.i18n.t("lbl_auto_pause"))
        self.auto_pause_switch = Gtk.Switch()
        self.auto_pause_switch.set_active(self.config.get("auto_pause_media", True))
        self.auto_pause_switch.connect("notify::active", self.auto_save)
        switch_box5.pack_start(lbl_auto_pause, False, False, 0)
        switch_box5.pack_start(self.auto_pause_switch, False, False, 0)
        general_box.pack_start(switch_box5, False, False, 0)

        switch_box_rt = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_realtime = Gtk.Label(label=self.i18n.t("lbl_realtime"))
        self.realtime_switch = Gtk.Switch()
        self.realtime_switch.set_active(self.config.get("realtime_mode", True))
        self.realtime_switch.connect("notify::active", self.auto_save)
        switch_box_rt.pack_start(lbl_realtime, False, False, 0)
        switch_box_rt.pack_start(self.realtime_switch, False, False, 0)
        general_box.pack_start(switch_box_rt, False, False, 0)

        switch_box6 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_autostart = Gtk.Label(label=self.i18n.t("lbl_autostart"))
        self.autostart_switch = Gtk.Switch()
        autostart_path = os.path.expanduser("~/.config/autostart/dictate-daemon.desktop")
        self.autostart_switch.set_active(os.path.exists(autostart_path))
        self.autostart_switch.connect("notify::active", self.auto_save)
        switch_box6.pack_start(lbl_autostart, False, False, 0)
        switch_box6.pack_start(self.autostart_switch, False, False, 0)
        general_box.pack_start(switch_box6, False, False, 0)
        
        switch_box7 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_notifications = Gtk.Label(label=self.i18n.t("lbl_notifications"))
        self.notifications_switch = Gtk.Switch()
        self.notifications_switch.set_active(self.config.get("show_notifications", True))
        self.notifications_switch.connect("notify::active", self.auto_save)
        switch_box7.pack_start(lbl_notifications, False, False, 0)
        switch_box7.pack_start(self.notifications_switch, False, False, 0)
        general_box.pack_start(switch_box7, False, False, 0)

        switch_box8 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_restore_focus = Gtk.Label(label=self.i18n.t("lbl_restore_focus"))
        self.restore_focus_switch = Gtk.Switch()
        self.restore_focus_switch.set_active(self.config.get("restore_window_focus", False))
        self.restore_focus_switch.connect("notify::active", self.auto_save)
        switch_box8.pack_start(lbl_restore_focus, False, False, 0)
        switch_box8.pack_start(self.restore_focus_switch, False, False, 0)
        general_box.pack_start(switch_box8, False, False, 0)
        
        # Tab 2: IA / LLM
        ia_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        ia_box.set_border_width(15)
        notebook.append_page(ia_box, Gtk.Label(label=self.i18n.t("tab_ai")))
        
        ia_box.pack_start(Gtk.Label(label=self.i18n.t("lbl_api_key"), xalign=0), False, False, 0)
        self.api_key_entry = Gtk.Entry()
        self.api_key_entry.set_text(self.config.get("api_key", ""))
        self.api_key_entry.set_visibility(False)
        self.api_key_entry.connect("focus-out-event", self.auto_save)
        ia_box.pack_start(self.api_key_entry, False, False, 0)
        
        ia_box.pack_start(Gtk.Label(label=self.i18n.t("lbl_model"), xalign=0), False, False, 0)
        self.model_entry = Gtk.Entry()
        self.model_entry.set_text(self.config.get("model", "gemma-4-26b-a4b-it"))
        self.model_entry.connect("focus-out-event", self.auto_save)
        ia_box.pack_start(self.model_entry, False, False, 0)
        
        # Timeout and Temperature horizontally
        ia_settings_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        
        timeout_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        timeout_box.pack_start(Gtk.Label(label=self.i18n.t("lbl_llm_timeout"), xalign=0), False, False, 0)
        self.llm_timeout_spin = Gtk.SpinButton.new_with_range(30, 600, 10)
        self.llm_timeout_spin.set_value(self.config.get("llm_timeout", 120))
        self.llm_timeout_spin.connect("value-changed", self.auto_save)
        timeout_box.pack_start(self.llm_timeout_spin, False, False, 0)
        ia_settings_box.pack_start(timeout_box, True, True, 0)
        
        temp_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        temp_box.pack_start(Gtk.Label(label=self.i18n.t("lbl_llm_temp"), xalign=0), False, False, 0)
        self.llm_temp_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 2.0, 0.1)
        self.llm_temp_scale.set_value(self.config.get("llm_temperature", 0.7))
        self.llm_temp_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.llm_temp_scale.connect("value-changed", self.auto_save)
        temp_box.pack_start(self.llm_temp_scale, False, False, 0)
        ia_settings_box.pack_start(temp_box, True, True, 0)
        
        ia_box.pack_start(ia_settings_box, False, False, 0)
        
        thinking_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_thinking = Gtk.Label(label=self.i18n.t("lbl_llm_thinking"))
        self.llm_thinking_switch = Gtk.Switch()
        self.llm_thinking_switch.set_active(self.config.get("llm_thinking", False))
        self.llm_thinking_switch.connect("notify::active", self.auto_save)
        thinking_box.pack_start(lbl_thinking, False, False, 0)
        thinking_box.pack_start(self.llm_thinking_switch, False, False, 0)
        ia_box.pack_start(thinking_box, False, False, 0)

        ia_box.pack_start(Gtk.Label(label=self.i18n.t("lbl_sys_prompt"), xalign=0), False, False, 0)
        self.base_prompt_view = Gtk.TextView()
        self.base_prompt_view.set_wrap_mode(Gtk.WrapMode.WORD)
        
        default_base_prompt = "You are a real-time voice dictation assistant.\nYour objective is to clean up the following voice-dictated text, correcting obvious speech recognition errors and punctuation, while keeping it as faithful to the original as possible.\nIf the text includes verbal formatting instructions (e.g. 'open parenthesis', 'new line', 'comma', 'period'), apply them.\nUse capitalization when appropriate and correct homophones based on context to make sense of the text without changing the original words or adding extra text.\nCRITICAL: You MUST reply in the EXACT SAME LANGUAGE as the dictated text. Do not translate it. For example, if the input is in Spanish, output in Spanish.\nReturn ONLY the corrected text, without greetings, explanations or translations."
        self.base_prompt_view.get_buffer().set_text(self.config.get("base_system_prompt", default_base_prompt))
        self.base_prompt_view.connect("focus-out-event", self.auto_save)
        
        scroll_base_prompt = Gtk.ScrolledWindow()
        scroll_base_prompt.set_shadow_type(Gtk.ShadowType.IN)
        scroll_base_prompt.add(self.base_prompt_view)
        ia_box.pack_start(scroll_base_prompt, True, True, 0)
        
        # Tab 3: Perfiles por Aplicación
        profiles_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        profiles_box.set_border_width(15)
        notebook.append_page(profiles_box, Gtk.Label(label=self.i18n.t("tab_apps")))
        
        # Left side: List of profiles
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        profiles_box.pack_start(left_box, False, False, 0)
        
        self.listbox = Gtk.ListBox()
        self.listbox.connect("row-selected", self.on_app_selected)
        scroll_list = Gtk.ScrolledWindow()
        scroll_list.set_size_request(200, -1)
        scroll_list.add(self.listbox)
        left_box.pack_start(scroll_list, True, True, 0)
        
        add_btn = Gtk.Button(label="Añadir App")
        add_btn.connect("clicked", self.on_add_app)
        left_box.pack_start(add_btn, False, False, 0)
        
        # Right side: Profile editor
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        profiles_box.pack_start(right_box, True, True, 0)
        
        self.current_app_label = Gtk.Label(label=self.i18n.t("msg_select_app"), xalign=0)
        self.current_app_label.set_markup(f"<b>{self.i18n.t('msg_select_app')}</b>")
        right_box.pack_start(self.current_app_label, False, False, 0)
        
        right_box.pack_start(Gtk.Label(label=self.i18n.t("lbl_sys_prompt"), xalign=0), False, False, 0)
        self.prompt_view = Gtk.TextView()
        self.prompt_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.prompt_view.connect("focus-out-event", self.auto_save_profile)
        scroll_prompt = Gtk.ScrolledWindow()
        scroll_prompt.set_shadow_type(Gtk.ShadowType.IN)
        scroll_prompt.add(self.prompt_view)
        right_box.pack_start(scroll_prompt, True, True, 0)
        
        self.vision_switch = Gtk.CheckButton(label=self.i18n.t("lbl_vision"))
        self.vision_switch.connect("toggled", self.auto_save_profile)
        right_box.pack_start(self.vision_switch, False, False, 0)
        
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        del_prof_btn = Gtk.Button(label=self.i18n.t("btn_delete"))
        del_prof_btn.connect("clicked", self.delete_current_profile)
        btn_box.pack_start(del_prof_btn, False, False, 0)
        right_box.pack_start(btn_box, False, False, 0)
        
        self.current_selected_app = None
        self.load_profiles()
        
        # Tab 4: Avanzado
        adv_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        adv_box.set_border_width(15)
        notebook.append_page(adv_box, Gtk.Label(label=self.i18n.t("tab_advanced")))

        ui_lang_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_ui_lang = Gtk.Label(label=self.i18n.t("ui_language"))
        self.ui_lang_combo = Gtk.ComboBoxText()
        self.ui_lang_combo.append("en", "English")
        self.ui_lang_combo.append("es", "Español")
        self.ui_lang_combo.append("fr", "Français")
        self.ui_lang_combo.append("de", "Deutsch")
        self.ui_lang_combo.set_active_id(self.config.get("ui_language", "en"))
        self.ui_lang_combo.connect("changed", self.on_ui_language_changed)
        ui_lang_box.pack_start(lbl_ui_lang, False, False, 0)
        ui_lang_box.pack_start(self.ui_lang_combo, False, False, 0)
        adv_box.pack_start(ui_lang_box, False, False, 0)

        chunk_stride_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_chunk_stride = Gtk.Label(label=self.i18n.t("lbl_chunk_stride"))
        self.chunk_stride_spin = Gtk.SpinButton.new_with_range(5.0, 30.0, 1.0)
        self.chunk_stride_spin.set_value(self.config.get("chunk_stride", 15.0))
        self.chunk_stride_spin.connect("value-changed", self.auto_save)
        chunk_stride_box.pack_start(lbl_chunk_stride, False, False, 0)
        chunk_stride_box.pack_start(self.chunk_stride_spin, False, False, 0)
        adv_box.pack_start(chunk_stride_box, False, False, 0)

        chunk_overlap_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_chunk_overlap = Gtk.Label(label=self.i18n.t("lbl_chunk_overlap"))
        self.chunk_overlap_spin = Gtk.SpinButton.new_with_range(0.0, 10.0, 0.5)
        self.chunk_overlap_spin.set_value(self.config.get("chunk_overlap", 2.0))
        self.chunk_overlap_spin.connect("value-changed", self.auto_save)
        chunk_overlap_box.pack_start(lbl_chunk_overlap, False, False, 0)
        chunk_overlap_box.pack_start(self.chunk_overlap_spin, False, False, 0)
        adv_box.pack_start(chunk_overlap_box, False, False, 0)

        chunk_tol_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_chunk_tol = Gtk.Label(label=self.i18n.t("lbl_chunk_tolerance"))
        self.chunk_tol_spin = Gtk.SpinButton.new_with_range(0.0, 2.0, 0.1)
        self.chunk_tol_spin.set_value(self.config.get("chunk_tolerance", 1.0))
        self.chunk_tol_spin.connect("value-changed", self.auto_save)
        chunk_tol_box.pack_start(lbl_chunk_tol, False, False, 0)
        chunk_tol_box.pack_start(self.chunk_tol_spin, False, False, 0)
        adv_box.pack_start(chunk_tol_box, False, False, 0)

        vad_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_vad = Gtk.Label(label=self.i18n.t("lbl_vad"))
        self.vad_switch = Gtk.Switch()
        self.vad_switch.set_active(self.config.get("vad_filter", False))
        self.vad_switch.connect("notify::active", self.auto_save)
        vad_box.pack_start(lbl_vad, False, False, 0)
        vad_box.pack_start(self.vad_switch, False, False, 0)
        adv_box.pack_start(vad_box, False, False, 0)

        lang_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_lang = Gtk.Label(label=self.i18n.t("transcription_language"))
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
        lang_box.pack_start(lbl_lang, False, False, 0)
        lang_box.pack_start(self.lang_combo, False, False, 0)
        adv_box.pack_start(lang_box, False, False, 0)

        beam_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_beam = Gtk.Label(label=self.i18n.t("lbl_beam"))
        self.beam_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 10, 1)
        self.beam_scale.set_value(self.config.get("beam_size", 5))
        self.beam_scale.set_digits(0)
        self.beam_scale.connect("value-changed", self.auto_save)
        beam_box.pack_start(lbl_beam, False, False, 0)
        beam_box.pack_start(self.beam_scale, True, True, 0)
        adv_box.pack_start(beam_box, False, False, 0)

        temp_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_temp = Gtk.Label(label=self.i18n.t("lbl_temp"))
        self.temp_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.1)
        self.temp_scale.set_value(self.config.get("temperature", 0.0))
        self.temp_scale.set_digits(1)
        self.temp_scale.connect("value-changed", self.auto_save)
        temp_box.pack_start(lbl_temp, False, False, 0)
        temp_box.pack_start(self.temp_scale, True, True, 0)
        adv_box.pack_start(temp_box, False, False, 0)

        # UI Options
        ui_opts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        lbl_ui_opts = Gtk.Label(label="Desktop Integration", xalign=0)
        lbl_ui_opts.set_markup(f"<b>{lbl_ui_opts.get_text()}</b>")
        ui_opts_box.pack_start(lbl_ui_opts, False, False, 10)
        
        self.use_appindicator_check = Gtk.CheckButton(label="Legacy Tray Icon (AppIndicator)")
        self.use_appindicator_check.set_active(self.config.get("use_appindicator", True))
        self.use_appindicator_check.connect("toggled", self.auto_save)
        ui_opts_box.pack_start(self.use_appindicator_check, False, False, 0)
        
        self.use_gnome_ext_check = Gtk.CheckButton(label="GNOME Shell Extension (Top Bar)")
        self.use_gnome_ext_check.set_active(self.config.get("use_gnome_ext", False))
        self.use_gnome_ext_check.connect("toggled", self.on_gnome_ext_toggle)
        ui_opts_box.pack_start(self.use_gnome_ext_check, False, False, 0)
        
        adv_box.pack_start(ui_opts_box, False, False, 10)
        
        # Tab 5: Gestor de Modelos
        models_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        models_box.set_border_width(15)
        notebook.append_page(models_box, Gtk.Label(label=self.i18n.t("tab_models")))
        
        scroll_models = Gtk.ScrolledWindow()
        scroll_models.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        models_box.pack_start(scroll_models, True, True, 0)
        
        self.models_listbox = Gtk.ListBox()
        self.models_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll_models.add(self.models_listbox)
        
        self.refresh_models_list()

        self.show_all()
        
    def on_delete_event(self, widget, event):
        self.hide()
        return True

    def refresh_models_list(self):
        for child in self.models_listbox.get_children():
            self.models_listbox.remove(child)
            
        models = ["tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en", "large-v1", "large-v2", "large-v3", "large"]
        active_model = self.config.get("whisper_model_size", "medium")
        
        for m in models:
            row = Gtk.ListBoxRow()
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.add(hbox)
            
            # Name
            name_lbl = Gtk.Label(label=m, xalign=0)
            if m == active_model:
                name_lbl.set_markup(f"<b>{m}</b> {self.i18n.t('active_model')}")
            hbox.pack_start(name_lbl, True, True, 10)
            
            # Status
            hf_path = os.path.expanduser(f"~/.cache/huggingface/hub/models--Systran--faster-whisper-{m}")
            downloaded = os.path.exists(hf_path)
            status_str = self.i18n.t("model_downloaded") if downloaded else self.i18n.t("model_not_downloaded")
            status_lbl = Gtk.Label(label=status_str)
            hbox.pack_start(status_lbl, False, False, 10)
            
            # Button
            btn = Gtk.Button(label=self.i18n.t("btn_activate"))
            if m == active_model:
                btn.set_sensitive(False)
            btn.connect("clicked", self.on_activate_model_clicked, m)
            hbox.pack_start(btn, False, False, 10)
            
            self.models_listbox.add(row)
        self.models_listbox.show_all()

    def on_activate_model_clicked(self, widget, model_name):
        self.config["whisper_model_size"] = model_name
        self.auto_save()
        self.refresh_models_list()

    def on_gnome_ext_toggle(self, switch):
        if self._updating_ui: return
        self.auto_save()
        import subprocess
        uuid = "com.kirulab.dictate@kirulab.com"
        if switch.get_active():
            subprocess.Popen(["gnome-extensions", "enable", uuid])
        else:
            subprocess.Popen(["gnome-extensions", "disable", uuid])
        if self.daemon_ref:
            self.daemon_ref.save_config()

    def load_config(self):
        if self.daemon_ref:
            return self.daemon_ref.config.copy()
        return {}

    def update_ui_from_config(self, new_config):
        self._updating_ui = True
        self.config = new_config
        
        self.auto_send_switch.set_active(self.config.get("auto_send", False))
        self.ai_enabled_switch.set_active(self.config.get("ai_enabled", False))
        self.hide_bubble_switch.set_active(self.config.get("hide_bubble", False))
        self.auto_pause_switch.set_active(self.config.get("auto_pause_media", True))
        if hasattr(self, 'realtime_switch'):
            self.realtime_switch.set_active(self.config.get("realtime_mode", True))
        if hasattr(self, 'notifications_switch'):
            self.notifications_switch.set_active(self.config.get("show_notifications", True))
        
        self.api_key_entry.set_text(self.config.get("api_key", ""))
        self.model_entry.set_text(self.config.get("model", "gemma-4-26b-a4b-it"))
        
        if hasattr(self, 'llm_timeout_spin'):
            self.llm_timeout_spin.set_value(self.config.get("llm_timeout", 120))
            self.llm_temp_scale.set_value(self.config.get("llm_temperature", 0.7))
            self.llm_thinking_switch.set_active(self.config.get("llm_thinking", False))
        
        if hasattr(self, 'vad_switch'):
            self.chunk_stride_spin.set_value(self.config.get("chunk_stride", 15.0))
            self.chunk_overlap_spin.set_value(self.config.get("chunk_overlap", 2.0))
            self.chunk_tol_spin.set_value(self.config.get("chunk_tolerance", 1.0))
            self.vad_switch.set_active(self.config.get("vad_filter", False))
            self.lang_combo.set_active_id(self.config.get("language", "auto"))
            self.ui_lang_combo.set_active_id(self.config.get("ui_language", "en"))
            self.beam_scale.set_value(self.config.get("beam_size", 5))
            self.temp_scale.set_value(self.config.get("temperature", 0.0))
        
        self._updating_ui = False

    def on_ui_language_changed(self, combo, *args):
        if self._updating_ui: return
        self.auto_save()
        # To reflect UI language changes immediately, we restart the UI by telling the daemon
        if self.daemon_ref:
            GLib.idle_add(self.daemon_ref.restart_config_window)

    def auto_save(self, *args):
        if self._updating_ui: return
        
        self.config["auto_send"] = self.auto_send_switch.get_active()
        self.config["ai_enabled"] = self.ai_enabled_switch.get_active()
        self.config["hide_bubble"] = self.hide_bubble_switch.get_active()
        self.config["auto_pause_media"] = self.auto_pause_switch.get_active()
        if hasattr(self, 'realtime_switch'):
            self.config["realtime_mode"] = self.realtime_switch.get_active()
        if hasattr(self, 'notifications_switch'):
            self.config["show_notifications"] = self.notifications_switch.get_active()
        if hasattr(self, 'restore_focus_switch'):
            self.config["restore_window_focus"] = self.restore_focus_switch.get_active()

        if hasattr(self, 'use_appindicator_check'):
            self.config["use_appindicator"] = self.use_appindicator_check.get_active()
            self.config["use_gnome_ext"] = self.use_gnome_ext_check.get_active()

        # Handle autostart desktop file
        autostart_dir = os.path.expanduser("~/.config/autostart")
        autostart_path = os.path.join(autostart_dir, "dictate-daemon.desktop")
        if self.autostart_switch.get_active():
            os.makedirs(autostart_dir, exist_ok=True)
            install_dir = os.path.expanduser("~/.local/share/dictate-whisper")
            desktop_content = f"""[Desktop Entry]
Type=Application
Name=OpenDictate
Comment=Background daemon for global voice dictation using faster-whisper
Exec={install_dir}/.venv/bin/python {install_dir}/dictate-daemon.py
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
        
        # Guardar Model Settings
        self.config["api_key"] = self.api_key_entry.get_text().strip()
        self.config["model"] = self.model_entry.get_text().strip()
        if hasattr(self, 'llm_timeout_spin'):
            self.config["llm_timeout"] = int(self.llm_timeout_spin.get_value())
            self.config["llm_temperature"] = float(self.llm_temp_scale.get_value())
            self.config["llm_thinking"] = self.llm_thinking_switch.get_active()
        
        # Guardar Configuración Avanzada si existen los widgets
        if hasattr(self, 'vad_switch'):
            self.config["chunk_stride"] = float(self.chunk_stride_spin.get_value())
            self.config["chunk_overlap"] = float(self.chunk_overlap_spin.get_value())
            self.config["chunk_tolerance"] = float(self.chunk_tol_spin.get_value())
            self.config["vad_filter"] = self.vad_switch.get_active()
            self.config["language"] = self.lang_combo.get_active_id()
            self.config["ui_language"] = self.ui_lang_combo.get_active_id()
            self.config["beam_size"] = int(self.beam_scale.get_value())
            self.config["temperature"] = float(self.temp_scale.get_value())
        
        buf = self.base_prompt_view.get_buffer()
        start, end = buf.get_bounds()
        self.config["base_system_prompt"] = buf.get_text(start, end, True).strip()
        
        if self.on_config_saved:
            self.on_config_saved(self.config)

    def load_profiles(self):
        for child in self.listbox.get_children():
            self.listbox.remove(child)
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT app_class FROM app_profiles")
            for row in cursor.fetchall():
                row_widget = Gtk.ListBoxRow()
                lbl = Gtk.Label(label=row[0], xalign=0, margin=10)
                row_widget.add(lbl)
                row_widget.app_class = row[0]
                self.listbox.add(row_widget)
            conn.close()
            self.listbox.show_all()
        except Exception as e:
            print("Error loading profiles:", e)

    def on_app_selected(self, listbox, row):
        if not row:
            self._updating_ui = True
            self.current_selected_app = None
            self.current_app_label.set_markup(f"<b>{self.i18n.t('msg_select_app')}</b>")
            self.prompt_view.get_buffer().set_text("")
            self.vision_switch.set_active(False)
            self._updating_ui = False
            return
            
        self._updating_ui = True
        self.current_selected_app = row.app_class
        self.current_app_label.set_markup(f"<b>Perfil: {self.current_selected_app}</b>")
        
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

    def get_open_apps(self):
        apps = set()
        try:
            import pyatspi
            desktop = pyatspi.Registry.getDesktop(0)
            for app in desktop:
                if not app: continue
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

    def on_add_app(self, btn):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Nueva Aplicación"
        )
        dialog.format_secondary_text("Selecciona una aplicación abierta o escribe su identificador:")
        
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
            import re
            match = re.search(r'\[(.*?)\]$', raw_text)
            if match:
                app_name = match.group(1).strip()
        
        if response == Gtk.ResponseType.OK and app_name:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO app_profiles (app_class, system_prompt, enable_vision) VALUES (?, '', 0)", (app_name,))
                conn.commit()
                conn.close()
                self.load_profiles()
            except Exception as e:
                self.show_message("Error al añadir aplicación", str(e))

    def auto_save_profile(self, *args):
        if self._updating_ui or not self.current_selected_app:
            return
            
        buffer = self.prompt_view.get_buffer()
        start, end = buffer.get_bounds()
        prompt = buffer.get_text(start, end, True).strip()
        vision = 1 if self.vision_switch.get_active() else 0
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE app_profiles SET system_prompt = ?, enable_vision = ? WHERE app_class = ?", (prompt, vision, self.current_selected_app))
            conn.commit()
            conn.close()
        except Exception as e:
            print("Auto-save profile error:", e)

    def delete_current_profile(self, btn):
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

    def show_message(self, title, message):
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

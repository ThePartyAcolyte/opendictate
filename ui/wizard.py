"""
First-run Onboarding & Setup Wizard for OpenDictate.

Guides the user through language selection, hardware diagnostics, Whisper model recommendations,
desktop integration selection (GNOME vs Tray AppIndicator), visual floating bubble mode,
Gemini / Gemma AI cleanup setup, OpenDeck plugin installation, and core preferences.
"""

import os
import shutil
import subprocess
import webbrowser
from typing import Dict, Any, Callable, Optional

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

from core.hardware import (
    get_system_ram_gb,
    get_gpu_info,
    detect_desktop_environment,
    recommend_whisper_model
)
from core.voice_commands import VoiceCommandManager
from core.aec import EchoCancelManager, AcousticCalibrator
from i18n import get_translator


WIZARD_CSS = b"""
/* OpenDictate Wizard Modern Dark UI (Matching Settings) */
window.wizard-window {
    background-color: #1e1e1e;
    color: #e0e0e0;
}

.wizard-header {
    background-color: #161616;
    padding: 16px 24px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.wizard-title {
    font-size: 16px;
    font-weight: bold;
    color: #ffffff;
}

.wizard-subtitle {
    font-size: 12px;
    color: #888888;
}

.step-indicator {
    font-size: 11px;
    font-weight: bold;
    color: #666666;
    padding: 4px 8px;
    border-radius: 6px;
    transition: all 150ms ease;
}

.step-indicator.active {
    color: #ffffff;
    background-color: rgba(53, 132, 228, 0.25);
    font-weight: bold;
}

.step-indicator.completed {
    color: #57e389;
}

.wizard-card {
    background-color: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 10px;
    padding: 14px 18px;
    margin: 6px 0px;
}

.selectable-card {
    background-color: rgba(255, 255, 255, 0.035);
    border: 2px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    padding: 12px;
    transition: all 150ms ease;
}

.selectable-card:hover {
    background-color: rgba(255, 255, 255, 0.06);
    border-color: rgba(255, 255, 255, 0.2);
}

.selectable-card.selected {
    border-color: #3584e4;
    background-color: rgba(53, 132, 228, 0.08);
}

.diag-badge {
    background-color: rgba(255, 255, 255, 0.08);
    color: #e0e0e0;
    font-size: 12px;
    font-weight: bold;
    padding: 4px 10px;
    border-radius: 6px;
}

.diag-badge-gpu {
    background-color: rgba(87, 227, 137, 0.15);
    color: #57e389;
    font-size: 12px;
    font-weight: bold;
    padding: 4px 10px;
    border-radius: 6px;
}

.wizard-footer {
    background-color: #161616;
    padding: 12px 24px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.btn-primary {
    background-color: #3584e4;
    color: #ffffff;
    font-weight: bold;
    border-radius: 6px;
    padding: 6px 20px;
}

.btn-finish {
    background-color: #57e389;
    color: #121212;
    font-weight: bold;
    border-radius: 6px;
    padding: 6px 22px;
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
"""


class FirstRunWizard(Gtk.Window):
    """Modern step-by-step initial configuration and onboarding wizard."""

    def __init__(
        self,
        config_manager: Any,
        on_finish: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> None:
        """Initialize onboarding wizard window and load system diagnostics.

        Args:
            config_manager: ConfigManager instance to load and persist configurations.
            on_finish: Optional callback invoked when user finishes setup with final config.
        """
        super().__init__(title="OpenDictate")
        self.set_default_size(760, 600)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.get_style_context().add_class("wizard-window")

        self.config_manager = config_manager
        self.config = self.config_manager.load_config() if self.config_manager else {}
        self.on_finish = on_finish

        self.selected_lang = self.config.get("ui_language", "es")
        self.i18n = get_translator(self.selected_lang)

        # Hardware diagnostics
        self.ram_gb = get_system_ram_gb()
        self.gpu_info = get_gpu_info()
        self.de_name, self.is_gnome = detect_desktop_environment()
        self.rec_model, self.rec_label_key, self.rec_desc_key = recommend_whisper_model(
            self.ram_gb, self.gpu_info["has_gpu"]
        )

        self.voice_commands = VoiceCommandManager(self.config)
        self.aec = EchoCancelManager()
        self.wizard_cmd_labels: Dict[str, Gtk.Label] = {}

        self.selected_bubble_mode = "text" if self.is_gnome else "interactive"
        self.current_step = 0
        self.total_steps = 8

        self._apply_css()
        self._build_ui()
        self.show_all()

    def _apply_css(self) -> None:
        """Inject modern dark styling into application screen style context."""
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(WIZARD_CSS)
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _build_ui(self) -> None:
        """Construct wizard header, breadcrumb navigation, content stack, and footer."""
        for child in self.get_children():
            self.remove(child)

        self.main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(self.main_vbox)

        # ---------------------------------------------------------
        # Header
        # ---------------------------------------------------------
        self.header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.header_box.get_style_context().add_class("wizard-header")

        self.title_lbl = Gtk.Label(label=self.i18n.t("wizard_welcome_title"), xalign=0)
        self.title_lbl.get_style_context().add_class("wizard-title")
        self.header_box.pack_start(self.title_lbl, False, False, 0)

        self.sub_lbl = Gtk.Label(label=self.i18n.t("wizard_welcome_subtitle"), xalign=0)
        self.sub_lbl.get_style_context().add_class("wizard-subtitle")
        self.header_box.pack_start(self.sub_lbl, False, False, 0)

        # Steps breadcrumb
        self.steps_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.steps_box.set_margin_top(8)
        self.step_labels = []
        step_names = [
            self.i18n.t("wizard_step_language"),
            self.i18n.t("wizard_step_hardware"),
            self.i18n.t("wizard_step_integration"),
            self.i18n.t("wizard_step_voice_commands"),
            self.i18n.t("wizard_step_ai"),
            self.i18n.t("wizard_step_shortcuts"),
            self.i18n.t("wizard_step_bubble"),
            self.i18n.t("wizard_step_finish"),
        ]
        for i, name in enumerate(step_names):
            lbl = Gtk.Label(label=f"{i+1}. {name}")
            lbl.get_style_context().add_class("step-indicator")
            self.steps_box.pack_start(lbl, False, False, 0)
            self.step_labels.append(lbl)

        self.header_box.pack_start(self.steps_box, False, False, 0)
        self.main_vbox.pack_start(self.header_box, False, False, 0)

        # ---------------------------------------------------------
        # Content Stack
        # ---------------------------------------------------------
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(200)
        self.main_vbox.pack_start(self.stack, True, True, 0)

        # Build 8 Pages in logical re-ordered flow
        self._build_page_language()        # Step 0
        self._build_page_hardware()        # Step 1
        self._build_page_integration()     # Step 2
        self._build_page_voice_commands()  # Step 3
        self._build_page_ai()              # Step 4
        self._build_page_shortcuts()       # Step 5
        self._build_page_bubble()          # Step 6
        self._build_page_finish()          # Step 7

        # ---------------------------------------------------------
        # Footer
        # ---------------------------------------------------------
        footer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        footer_box.get_style_context().add_class("wizard-footer")

        self.btn_back = Gtk.Button(label=self.i18n.t("wizard_btn_back"))
        self.btn_back.connect("clicked", self._on_back_clicked)
        self.btn_back.set_sensitive(False)
        footer_box.pack_start(self.btn_back, False, False, 0)

        footer_box.pack_start(Gtk.Box(), True, True, 0)  # Spacer

        self.btn_next = Gtk.Button(label=self.i18n.t("wizard_btn_next"))
        self.btn_next.get_style_context().add_class("btn-primary")
        self.btn_next.connect("clicked", self._on_next_clicked)
        footer_box.pack_end(self.btn_next, False, False, 0)

        self.main_vbox.pack_end(footer_box, False, False, 0)
        self._update_step_view()

    # -------------------------------------------------------------------------
    # Step 0: Language Selection & Welcome (Multi-language)
    # -------------------------------------------------------------------------
    def _build_page_language(self) -> None:
        """Construct Step 0 language selection radio list."""
        scroll = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_left(28)
        box.set_margin_right(28)
        scroll.add(box)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.get_style_context().add_class("wizard-card")

        title = Gtk.Label(xalign=0)
        title.set_markup(f"<b>{GLib.markup_escape_text(self.i18n.t('wizard_lang_title'))}</b>")
        card.pack_start(title, False, False, 0)

        desc = Gtk.Label(label=self.i18n.t("wizard_lang_subtitle"), xalign=0)
        desc.set_line_wrap(True)
        card.pack_start(desc, False, False, 0)

        # Multi-language Radio Group
        languages = [
            ("es", "Español (Spanish)"),
            ("en", "English (English)"),
            ("fr", "Français (French)"),
            ("de", "Deutsch (German)"),
        ]

        self.lang_radios = {}
        first_radio = None
        for code, label_text in languages:
            if first_radio is None:
                r = Gtk.RadioButton.new_with_label(None, label_text)
                first_radio = r
            else:
                r = Gtk.RadioButton.new_with_label_from_widget(first_radio, label_text)

            if self.selected_lang == code:
                r.set_active(True)
            r.connect("toggled", self._on_language_toggled, code)
            card.pack_start(r, False, False, 3)
            self.lang_radios[code] = r

        box.pack_start(card, False, False, 0)
        self.stack.add_named(scroll, "step_0")

    def _on_language_toggled(self, button: Gtk.RadioButton, lang: str) -> None:
        """Handle language radio selection toggle and reload localized strings.

        Args:
            button: RadioButton emitting signal.
            lang: Selected language code (e.g. 'es', 'en', 'de', 'fr').
        """
        if button.get_active() and self.selected_lang != lang:
            self.selected_lang = lang
            self.i18n = get_translator(lang)
            self.config["ui_language"] = lang
            saved_step = self.current_step
            self._build_ui()
            self.current_step = saved_step
            self._update_step_view()
            self.show_all()

    # -------------------------------------------------------------------------
    # Step 1: Hardware & Whisper Model
    # -------------------------------------------------------------------------
    def _build_page_hardware(self) -> None:
        """Construct Step 1 hardware diagnostic report and model recommendation view."""
        scroll = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_left(28)
        box.set_margin_right(28)
        scroll.add(box)

        # Diag Card
        card_diag = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card_diag.get_style_context().add_class("wizard-card")

        card_title = Gtk.Label(xalign=0)
        card_title.set_markup(f"<b>{GLib.markup_escape_text(self.i18n.t('wizard_hw_title'))}</b>")
        card_diag.pack_start(card_title, False, False, 0)

        badge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        ram_badge = Gtk.Label(label=f"💾 {self.i18n.t('wizard_ram_detected', self.ram_gb)}")
        ram_badge.get_style_context().add_class("diag-badge")
        badge_box.pack_start(ram_badge, False, False, 0)

        gpu_name = self.gpu_info.get("gpu_name", "CPU Only")
        has_gpu = self.gpu_info.get("has_gpu", False)
        cuda_ready = self.gpu_info.get("cuda_ready", False)

        if has_gpu and cuda_ready:
            gpu_badge_text = self.i18n.t("wizard_badge_cuda_accelerated", gpu_name)
            gpu_badge_class = "diag-badge-gpu"
        elif has_gpu:
            gpu_badge_text = self.i18n.t("wizard_badge_cpu_mode", gpu_name)
            gpu_badge_class = "diag-badge"
        else:
            gpu_badge_text = f"⚙️ {gpu_name}"
            gpu_badge_class = "diag-badge"

        gpu_badge = Gtk.Label(label=gpu_badge_text)
        gpu_badge.get_style_context().add_class(gpu_badge_class)
        badge_box.pack_start(gpu_badge, False, False, 0)

        de_badge = Gtk.Label(label=f"🖥️ {self.i18n.t('wizard_de_detected', self.de_name)}")
        de_badge.get_style_context().add_class("diag-badge")
        badge_box.pack_start(de_badge, False, False, 0)

        card_diag.pack_start(badge_box, False, False, 4)

        if has_gpu and not cuda_ready:
            cuda_hint = Gtk.Label(label=self.i18n.t("wizard_cuda_missing_libs"), xalign=0)
            cuda_hint.get_style_context().add_class("row-subtitle")
            card_diag.pack_start(cuda_hint, False, False, 2)

        box.pack_start(card_diag, False, False, 0)

        # Model Recommendation Card
        card_rec = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card_rec.get_style_context().add_class("wizard-card")

        rec_label_text = self.i18n.t(self.rec_label_key)
        rec_title = Gtk.Label(xalign=0)
        rec_title.set_markup(f"<b>{GLib.markup_escape_text(self.i18n.t('wizard_recommended_model', rec_label_text))}</b>")
        card_rec.pack_start(rec_title, False, False, 0)

        rec_desc_lbl = Gtk.Label(label=self.i18n.t(self.rec_desc_key), xalign=0)
        rec_desc_lbl.set_line_wrap(True)
        card_rec.pack_start(rec_desc_lbl, False, False, 0)

        # Model Selection Combo
        model_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        model_hbox.set_margin_top(8)
        model_lbl = Gtk.Label(label=self.i18n.t("wizard_select_model"), xalign=0)
        model_hbox.pack_start(model_lbl, False, False, 0)

        self.model_combo = Gtk.ComboBoxText()
        models = [
            ("tiny", self.i18n.t("wizard_model_opt_tiny")),
            ("base", self.i18n.t("wizard_model_opt_base")),
            ("small", self.i18n.t("wizard_model_opt_small")),
            ("medium", self.i18n.t("wizard_model_opt_medium")),
            ("large-v3", self.i18n.t("wizard_model_opt_large")),
        ]
        for mid, mlabel in models:
            self.model_combo.append(mid, mlabel)
        self.model_combo.set_active_id(self.rec_model)
        model_hbox.pack_end(self.model_combo, True, True, 0)

        card_rec.pack_start(model_hbox, False, False, 0)
        box.pack_start(card_rec, False, False, 0)

        self.stack.add_named(scroll, "step_1")

    # -------------------------------------------------------------------------
    # Step 2: Desktop Integration (Binary Exclusive Choice)
    # -------------------------------------------------------------------------
    def _build_page_integration(self) -> None:
        """Construct Step 2 desktop integration selector (GNOME Extension vs Tray AppIndicator)."""
        scroll = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_left(28)
        box.set_margin_right(28)
        scroll.add(box)

        card_integ = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card_integ.get_style_context().add_class("wizard-card")

        integ_title = Gtk.Label(xalign=0)
        integ_title.set_markup(f"<b>{GLib.markup_escape_text(self.i18n.t('wizard_integ_title'))}</b>")
        card_integ.pack_start(integ_title, False, False, 0)

        desc = Gtk.Label(label=self.i18n.t("wizard_integ_subtitle"), xalign=0)
        desc.set_line_wrap(True)
        card_integ.pack_start(desc, False, False, 0)

        # Binary Radio Group
        self.radio_gnome = Gtk.RadioButton.new_with_label(None, self.i18n.t("wizard_radio_gnome"))
        self.radio_tray = Gtk.RadioButton.new_with_label_from_widget(
            self.radio_gnome, self.i18n.t("wizard_radio_tray")
        )

        if self.is_gnome:
            self.radio_gnome.set_active(True)
        else:
            self.radio_gnome.set_sensitive(False)
            self.radio_gnome.set_label(self.i18n.t("wizard_gnome_disabled_note"))
            self.radio_tray.set_active(True)

        card_integ.pack_start(self.radio_gnome, False, False, 4)
        card_integ.pack_start(self.radio_tray, False, False, 4)

        box.pack_start(card_integ, False, False, 0)
        self.stack.add_named(scroll, "step_2")

    # -------------------------------------------------------------------------
    # Step 3: Voice Commands & Wake Word Enrollment
    # -------------------------------------------------------------------------
    def _build_page_voice_commands(self) -> None:
        """Construct Step 3 voice commands enrollment and AEC calibration."""
        scroll = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_left(28)
        box.set_margin_right(28)
        scroll.add(box)

        # Header card
        card_hdr = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card_hdr.get_style_context().add_class("wizard-card")

        t_lbl = Gtk.Label(label=self.i18n.t("wizard_voice_title"), xalign=0)
        t_lbl.get_style_context().add_class("card-title")
        card_hdr.pack_start(t_lbl, False, False, 0)

        s_lbl = Gtk.Label(label=self.i18n.t("wizard_voice_subtitle"), xalign=0)
        s_lbl.set_line_wrap(True)
        s_lbl.get_style_context().add_class("card-desc")
        card_hdr.pack_start(s_lbl, False, False, 0)

        # Switch to enable/disable
        sw_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        sw_box.set_margin_top(8)
        sw_lbl = Gtk.Label(label=self.i18n.t("lbl_voice_commands_enabled"), xalign=0)
        sw_lbl.get_style_context().add_class("card-title")
        sw_box.pack_start(sw_lbl, True, True, 0)

        self.sw_voice = Gtk.Switch()
        self.sw_voice.set_active(self.config.get("voice_commands_enabled", True))
        self.sw_voice.connect("notify::active", lambda sw, p: self.config.update({"voice_commands_enabled": sw.get_active()}))
        sw_box.pack_end(self.sw_voice, False, False, 0)
        card_hdr.pack_start(sw_box, False, False, 0)

        # Calibration Card (Piso de Ruido / Sensibilidad)
        card_noise = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card_noise.get_style_context().add_class("wizard-card")

        n_title = Gtk.Label(label=self.i18n.t("group_noise_calibration"), xalign=0)
        n_title.get_style_context().add_class("card-title")
        card_noise.pack_start(n_title, False, False, 0)

        n_desc = Gtk.Label(
            label=self.i18n.t("desc_noise_calibration"),
            xalign=0
        )
        n_desc.get_style_context().add_class("card-desc")
        card_noise.pack_start(n_desc, False, False, 0)

        n_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.wizard_noise_lbl = Gtk.Label(
            label=f"Piso: {self.config.get('voice_vad_noise_floor', 0.030):.3f} | Umbral: {self.config.get('voice_vad_threshold', 0.075):.3f}",
            xalign=0
        )
        self.wizard_noise_lbl.get_style_context().add_class("card-desc")
        n_row.pack_start(self.wizard_noise_lbl, True, True, 0)

        btn_calib_noise = Gtk.Button(label=self.i18n.t("btn_calibrate_noise"))
        btn_calib_noise.get_style_context().add_class("btn-secondary")
        btn_calib_noise.connect("clicked", self._on_wizard_calibrate_noise)
        n_row.pack_end(btn_calib_noise, False, False, 0)
        card_noise.pack_start(n_row, False, False, 0)

        box.pack_start(card_noise, False, False, 0)

        # 4 Commands card
        card_cmds = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card_cmds.get_style_context().add_class("wizard-card")

        action_keys = [
            ("START", "voice_cmd_start"),
            ("SEND", "voice_cmd_send"),
            ("PAUSE", "voice_cmd_pause"),
            ("CANCEL", "voice_cmd_cancel"),
        ]
        for action, str_key in action_keys:
            r_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            r_lbl = Gtk.Label(label=self.i18n.t(str_key), xalign=0)
            r_lbl.get_style_context().add_class("card-title")
            r_box.pack_start(r_lbl, True, True, 0)

            cnt = len(self.voice_commands.templates.get(action, []))
            cnt_lbl = Gtk.Label(label=f"{cnt}/3", xalign=1)
            cnt_lbl.get_style_context().add_class("dim-label")
            self.wizard_cmd_labels[action] = cnt_lbl
            r_box.pack_start(cnt_lbl, False, False, 4)

            rec_btn = Gtk.Button(label=self.i18n.t("btn_record_sample"))
            rec_btn.get_style_context().add_class("btn-secondary")
            rec_btn.connect("clicked", lambda b, act=action: self._record_wizard_sample(act, b))
            r_box.pack_start(rec_btn, False, False, 0)

            clr_btn = Gtk.Button(label=self.i18n.t("btn_clear_samples"))
            clr_btn.get_style_context().add_class("btn-danger-outline")
            clr_btn.connect("clicked", lambda b, act=action: self._clear_wizard_sample(act))
            r_box.pack_start(clr_btn, False, False, 0)

            card_cmds.pack_start(r_box, False, False, 0)

        box.pack_start(card_cmds, False, False, 0)

        # AEC Calibration card
        card_calib = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card_calib.get_style_context().add_class("wizard-card")

        calib_title = Gtk.Label(label=self.i18n.t("group_aec_calibration"), xalign=0)
        calib_title.get_style_context().add_class("card-title")
        card_calib.pack_start(calib_title, False, False, 0)

        c_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.calib_res_lbl = Gtk.Label(label="--", xalign=0)
        self.calib_res_lbl.get_style_context().add_class("card-desc")
        c_row.pack_start(self.calib_res_lbl, True, True, 0)

        calib_btn = Gtk.Button(label=self.i18n.t("btn_calibrate_aec"))
        calib_btn.get_style_context().add_class("btn-secondary")
        calib_btn.connect("clicked", self._on_wizard_calibrate_aec)
        c_row.pack_end(calib_btn, False, False, 0)
        card_calib.pack_start(c_row, False, False, 0)

        box.pack_start(card_calib, False, False, 0)

        self.stack.add_named(scroll, "step_3")

    # -------------------------------------------------------------------------
    # Step 4: AI Post-Processing & Gemini / Gemma Setup
    # -------------------------------------------------------------------------
    def _build_page_ai(self) -> None:
        """Construct Step 3 AI post-processing and Google Gemini API setup page."""
        scroll = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_left(28)
        box.set_margin_right(28)
        scroll.add(box)

        card_ai = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card_ai.get_style_context().add_class("wizard-card")

        ai_title = Gtk.Label(xalign=0)
        ai_title.set_markup(f"<b>{GLib.markup_escape_text(self.i18n.t('wizard_ai_title'))}</b>")
        card_ai.pack_start(ai_title, False, False, 0)

        what_desc = Gtk.Label(label=self.i18n.t("wizard_ai_what_desc"), xalign=0)
        what_desc.set_line_wrap(True)
        card_ai.pack_start(what_desc, False, False, 0)

        # Privacy Notice Label
        privacy_lbl = Gtk.Label(label=self.i18n.t("wizard_ai_privacy_note"), xalign=0)
        privacy_lbl.set_line_wrap(True)
        privacy_lbl.get_style_context().add_class("row-subtitle")
        card_ai.pack_start(privacy_lbl, False, False, 4)

        # Master Toggle Switch (Defaults to False)
        toggle_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        toggle_lbl = Gtk.Label(label=self.i18n.t("wizard_ai_toggle_enable"), xalign=0)
        toggle_lbl.get_style_context().add_class("row-title")
        toggle_hbox.pack_start(toggle_lbl, True, True, 0)

        self.ai_enable_switch = Gtk.Switch()
        initial_ai = bool(self.config.get("ai_enabled", False)) and bool(self.config.get("api_key", ""))
        self.ai_enable_switch.set_active(initial_ai)
        self.ai_enable_switch.connect("notify::active", self._on_ai_switch_toggled)
        toggle_hbox.pack_end(self.ai_enable_switch, False, False, 0)
        card_ai.pack_start(toggle_hbox, False, False, 4)

        # Sub-container for AI settings
        self.ai_details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.ai_details_box.set_sensitive(initial_ai)

        # Links Box
        links_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_get_key = Gtk.Button(label=f"🌐 {self.i18n.t('wizard_ai_get_key')}")
        btn_get_key.connect("clicked", lambda b: webbrowser.open("https://aistudio.google.com/app/apikey"))
        links_hbox.pack_start(btn_get_key, True, True, 0)

        btn_docs = Gtk.Button(label=f"📖 {self.i18n.t('wizard_ai_docs_link')}")
        btn_docs.connect("clicked", lambda b: webbrowser.open("https://ai.google.dev/gemini-api/docs/models/gemini"))
        links_hbox.pack_start(btn_docs, True, True, 0)
        self.ai_details_box.pack_start(links_hbox, False, False, 2)

        # API Key Entry Row
        key_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        key_lbl = Gtk.Label(label=self.i18n.t("wizard_ai_key_label"), xalign=0)
        key_hbox.pack_start(key_lbl, False, False, 0)

        self.api_key_entry = Gtk.Entry()
        self.api_key_entry.set_placeholder_text(self.i18n.t("wizard_ai_key_placeholder"))
        self.api_key_entry.set_visibility(False)
        self.api_key_entry.set_text(self.config.get("api_key", ""))
        key_hbox.pack_end(self.api_key_entry, True, True, 0)
        self.ai_details_box.pack_start(key_hbox, False, False, 2)

        # STT Engine Selection
        stt_backend_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        stt_backend_lbl = Gtk.Label(label=self.i18n.t("lbl_stt_backend"), xalign=0)
        stt_backend_row.pack_start(stt_backend_lbl, False, False, 0)

        self.stt_backend_combo = Gtk.ComboBoxText()
        self.stt_backend_combo.append("local_whisper", self.i18n.t("stt_backend_local"))
        self.stt_backend_combo.append("gemini_live", self.i18n.t("stt_backend_gemini_live"))
        self.stt_backend_combo.set_active_id(self.config.get("stt_backend", "local_whisper"))
        stt_backend_row.pack_end(self.stt_backend_combo, True, True, 0)
        self.ai_details_box.pack_start(stt_backend_row, False, False, 2)

        # Model Selector / Entry Row
        model_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        model_label = Gtk.Label(label=self.i18n.t("wizard_ai_model_label"), xalign=0)
        model_row.pack_start(model_label, False, False, 0)

        self.ai_model_combo = Gtk.ComboBoxText.new_with_entry()
        suggested_models = [
            "gemini-3.1-flash-live-preview",
            "gemma-4-26b-a4b-it",
        ]
        for mod in suggested_models:
            self.ai_model_combo.append_text(mod)

        current_model = self.config.get("model", "gemini-3.1-flash-live-preview")
        self.ai_model_combo.get_child().set_text(current_model)
        model_row.pack_end(self.ai_model_combo, True, True, 0)
        self.ai_details_box.pack_start(model_row, False, False, 2)

        # AI Model Tiers Explanation Label
        tiers_lbl = Gtk.Label(label=self.i18n.t("wizard_ai_tiers_info"), xalign=0)
        tiers_lbl.set_line_wrap(True)
        tiers_lbl.get_style_context().add_class("row-subtitle")
        self.ai_details_box.pack_start(tiers_lbl, False, False, 4)

        card_ai.pack_start(self.ai_details_box, False, False, 0)

        opt_note = Gtk.Label(label=self.i18n.t("wizard_ai_optional_note"), xalign=0)
        opt_note.get_style_context().add_class("row-subtitle")
        card_ai.pack_start(opt_note, False, False, 2)

        box.pack_start(card_ai, False, False, 0)
        self.stack.add_named(scroll, "step_4")

    def _on_ai_switch_toggled(self, switch: Gtk.Switch, gparam: Any) -> None:
        """Handle AI master toggle switch state change.

        Args:
            switch: Switch widget being toggled.
            gparam: GObject property parameter specification.
        """
        is_active = switch.get_active()
        if hasattr(self, 'ai_details_box'):
            self.ai_details_box.set_sensitive(is_active)
            if is_active and hasattr(self, 'api_key_entry'):
                self.api_key_entry.grab_focus()

    # -------------------------------------------------------------------------
    # Step 4: OpenDeck & Keyboard Shortcuts
    # -------------------------------------------------------------------------
    def _build_page_shortcuts(self) -> None:
        """Construct Step 4 shortcuts and OpenDeck plugin installation card."""
        scroll = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_left(28)
        box.set_margin_right(28)
        scroll.add(box)

        # OpenDeck Detection Card
        card_od = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card_od.get_style_context().add_class("wizard-card")

        od_title = Gtk.Label(xalign=0)
        od_title.set_markup(f"<b>{GLib.markup_escape_text(self.i18n.t('wizard_opendeck_hardware_title'))}</b>")
        card_od.pack_start(od_title, False, False, 0)

        opendeck_dir = os.path.expanduser("~/.config/opendeck")
        has_opendeck = os.path.exists(opendeck_dir)

        od_status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        if has_opendeck:
            od_badge = Gtk.Label(label=self.i18n.t("wizard_opendeck_detected"))
            od_badge.get_style_context().add_class("diag-badge-gpu")
        else:
            od_badge = Gtk.Label(label=self.i18n.t("wizard_opendeck_missing"))
            od_badge.get_style_context().add_class("diag-badge")
        od_status_box.pack_start(od_badge, False, False, 0)

        self.btn_wizard_opendeck = Gtk.Button(label=self.i18n.t("wizard_btn_install_opendeck"))
        self.btn_wizard_opendeck.connect("clicked", self._on_install_opendeck_in_wizard)
        od_status_box.pack_end(self.btn_wizard_opendeck, False, False, 0)

        card_od.pack_start(od_status_box, False, False, 4)
        box.pack_start(card_od, False, False, 0)

        # CLI Shortcuts Card
        card_cli = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card_cli.get_style_context().add_class("wizard-card")

        cli_title = Gtk.Label(xalign=0)
        cli_title.set_markup(f"<b>{GLib.markup_escape_text(self.i18n.t('wizard_shortcuts_list_title'))}</b>")
        card_cli.pack_start(cli_title, False, False, 0)

        cli_commands = [
            ("opendictate --toggle-record-send", self.i18n.t("cli_desc_toggle_record_send")),
            ("opendictate --settings", self.i18n.t("cli_desc_settings")),
            ("opendictate --record", self.i18n.t("cli_desc_record")),
            ("opendictate --cancel", self.i18n.t("cli_desc_cancel")),
            ("opendictate --send", self.i18n.t("cli_desc_send")),
            ("opendictate --finish-normal", self.i18n.t("cli_desc_finish_normal")),
            ("opendictate --finish-ai", self.i18n.t("cli_desc_finish_ai")),
        ]

        for cmd, desc in cli_commands:
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row_box.set_margin_top(2)
            row_box.set_margin_bottom(2)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            cmd_lbl = Gtk.Label(xalign=0)
            cmd_lbl.set_markup(f"<span font_family='monospace' weight='bold' foreground='#78aeed'>{cmd}</span>")
            vbox.pack_start(cmd_lbl, False, False, 0)
            desc_lbl = Gtk.Label(label=desc, xalign=0)
            desc_lbl.get_style_context().add_class("row-subtitle")
            vbox.pack_start(desc_lbl, False, False, 0)
            row_box.pack_start(vbox, True, True, 0)

            btn_copy = Gtk.Button(label=self.i18n.t("btn_copy"))
            btn_copy.connect("clicked", self._create_copy_callback(cmd))
            row_box.pack_end(btn_copy, False, False, 0)
            card_cli.pack_start(row_box, False, False, 0)

        box.pack_start(card_cli, False, False, 0)
        self.stack.add_named(scroll, "step_5")

    def _create_copy_callback(self, text: str):
        """Create a clipboard copy callback for shortcut command lines.

        Args:
            text: Command string to copy.

        Returns:
            Callback function taking a Gtk.Button.
        """
        def _cb(btn: Gtk.Button):
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(text, -1)
            btn.set_label(self.i18n.t("copied_toast"))
            GLib.timeout_add(1500, lambda: btn.set_label(self.i18n.t("btn_copy")))
        return _cb

    # -------------------------------------------------------------------------
    # Step 5: Floating Bubble Mode (2x2 Visual Grid with 4 Selectable Options)
    # -------------------------------------------------------------------------
    def _build_page_bubble(self) -> None:
        """Construct Step 5 2x2 visual card grid for bubble mode selection."""
        scroll = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_left(28)
        box.set_margin_right(28)
        scroll.add(box)

        header_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title = Gtk.Label(xalign=0)
        title.set_markup(f"<b>{GLib.markup_escape_text(self.i18n.t('wizard_bubble_title'))}</b>")
        header_card.pack_start(title, False, False, 0)

        desc = Gtk.Label(label=self.i18n.t("wizard_bubble_subtitle"), xalign=0)
        desc.set_line_wrap(True)
        header_card.pack_start(desc, False, False, 0)
        box.pack_start(header_card, False, False, 0)

        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(12)
        grid.set_column_homogeneous(True)
        grid.set_row_homogeneous(True)

        img_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "img")

        # 1. Card Solo Texto (OSD)
        self.card_text = Gtk.EventBox()
        card_text_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card_text_inner.get_style_context().add_class("selectable-card")

        lbl_text_title = Gtk.Label(xalign=0)
        lbl_text_title.set_markup(f"<b>{GLib.markup_escape_text(self.i18n.t('wizard_card_bubble_text_title'))}</b>")
        card_text_inner.pack_start(lbl_text_title, False, False, 0)

        img_text_path = os.path.join(img_dir, "bubble_preview_text.png")
        if os.path.exists(img_text_path):
            try:
                pixbuf_text = GdkPixbuf.Pixbuf.new_from_file_at_scale(img_text_path, 220, -1, True)
                card_text_inner.pack_start(Gtk.Image.new_from_pixbuf(pixbuf_text), False, False, 0)
            except Exception:
                pass

        lbl_text_desc = Gtk.Label(label=self.i18n.t("wizard_card_bubble_text_desc"), xalign=0)
        lbl_text_desc.set_line_wrap(True)
        lbl_text_desc.get_style_context().add_class("row-subtitle")
        card_text_inner.pack_start(lbl_text_desc, True, True, 0)

        self.card_text.add(card_text_inner)
        self.card_text.connect("button-press-event", lambda w, e: self._select_bubble_mode("text"))
        grid.attach(self.card_text, 0, 0, 1, 1)

        # 2. Card Cápsula con Controles y Texto
        self.card_interactive = Gtk.EventBox()
        card_inter_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card_inter_inner.get_style_context().add_class("selectable-card")

        lbl_inter_title = Gtk.Label(xalign=0)
        lbl_inter_title.set_markup(f"<b>{GLib.markup_escape_text(self.i18n.t('wizard_card_bubble_interactive_title'))}</b>")
        card_inter_inner.pack_start(lbl_inter_title, False, False, 0)

        img_inter_path = os.path.join(img_dir, "bubble_preview_interactive.png")
        if os.path.exists(img_inter_path):
            try:
                pixbuf_inter = GdkPixbuf.Pixbuf.new_from_file_at_scale(img_inter_path, 220, -1, True)
                card_inter_inner.pack_start(Gtk.Image.new_from_pixbuf(pixbuf_inter), False, False, 0)
            except Exception:
                pass

        lbl_inter_desc = Gtk.Label(label=self.i18n.t("wizard_card_bubble_interactive_desc"), xalign=0)
        lbl_inter_desc.set_line_wrap(True)
        lbl_inter_desc.get_style_context().add_class("row-subtitle")
        card_inter_inner.pack_start(lbl_inter_desc, True, True, 0)

        self.card_interactive.add(card_inter_inner)
        self.card_interactive.connect("button-press-event", lambda w, e: self._select_bubble_mode("interactive"))
        grid.attach(self.card_interactive, 1, 0, 1, 1)

        # 3. Card Solo Controles (Cápsula Compacta)
        self.card_compact = Gtk.EventBox()
        card_compact_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card_compact_inner.get_style_context().add_class("selectable-card")

        lbl_compact_title = Gtk.Label(xalign=0)
        lbl_compact_title.set_markup(f"<b>{GLib.markup_escape_text(self.i18n.t('wizard_card_bubble_compact_title'))}</b>")
        card_compact_inner.pack_start(lbl_compact_title, False, False, 0)

        img_compact_path = os.path.join(img_dir, "bubble_preview_compact.png")
        if os.path.exists(img_compact_path):
            try:
                pixbuf_compact = GdkPixbuf.Pixbuf.new_from_file_at_scale(img_compact_path, 220, -1, True)
                card_compact_inner.pack_start(Gtk.Image.new_from_pixbuf(pixbuf_compact), False, False, 0)
            except Exception:
                pass

        lbl_compact_desc = Gtk.Label(label=self.i18n.t("wizard_card_bubble_compact_desc"), xalign=0)
        lbl_compact_desc.set_line_wrap(True)
        lbl_compact_desc.get_style_context().add_class("row-subtitle")
        card_compact_inner.pack_start(lbl_compact_desc, True, True, 0)

        self.card_compact.add(card_compact_inner)
        self.card_compact.connect("button-press-event", lambda w, e: self._select_bubble_mode("compact"))
        grid.attach(self.card_compact, 0, 1, 1, 1)

        # 4. Card Sin Burbuja (Ocultar)
        self.card_none = Gtk.EventBox()
        card_none_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card_none_inner.get_style_context().add_class("selectable-card")

        lbl_none_title = Gtk.Label(xalign=0)
        lbl_none_title.set_markup(f"<b>{GLib.markup_escape_text(self.i18n.t('wizard_card_bubble_none_title'))}</b>")
        card_none_inner.pack_start(lbl_none_title, False, False, 0)

        icon_none = Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.DIALOG)
        icon_none.set_pixel_size(32)
        icon_none.set_margin_top(4)
        icon_none.set_margin_bottom(4)
        card_none_inner.pack_start(icon_none, False, False, 0)

        lbl_none_desc = Gtk.Label(label=self.i18n.t("wizard_card_bubble_none_desc"), xalign=0)
        lbl_none_desc.set_line_wrap(True)
        lbl_none_desc.get_style_context().add_class("row-subtitle")
        card_none_inner.pack_start(lbl_none_desc, True, True, 0)

        self.card_none.add(card_none_inner)
        self.card_none.connect("button-press-event", lambda w, e: self._select_bubble_mode("none"))
        grid.attach(self.card_none, 1, 1, 1, 1)

        box.pack_start(grid, True, True, 0)
        self._update_bubble_cards_ui()

        self.stack.add_named(scroll, "step_6")

    def _select_bubble_mode(self, mode: str) -> None:
        """Set active bubble mode and refresh card visual selection styles.

        Args:
            mode: Bubble mode identifier ('text', 'interactive', 'compact', 'none').
        """
        self.selected_bubble_mode = mode
        self._update_bubble_cards_ui()

    def _update_bubble_cards_ui(self) -> None:
        """Synchronize CSS active highlight classes across bubble mode preview cards."""
        cards = {
            "text": getattr(self, "card_text", None),
            "interactive": getattr(self, "card_interactive", None),
            "compact": getattr(self, "card_compact", None),
            "none": getattr(self, "card_none", None),
        }
        for mode, card_widget in cards.items():
            if card_widget and card_widget.get_child():
                ctx = card_widget.get_child().get_style_context()
                if self.selected_bubble_mode == mode:
                    ctx.add_class("selected")
                else:
                    ctx.remove_class("selected")

    # -------------------------------------------------------------------------
    # Step 6: General Preferences & Finish
    # -------------------------------------------------------------------------
    def _build_page_finish(self) -> None:
        """Construct Step 6 general preferences toggles and completion banner."""
        scroll = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_left(28)
        box.set_margin_right(28)
        scroll.add(box)

        card_pref = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card_pref.get_style_context().add_class("wizard-card")

        pref_title = Gtk.Label(xalign=0)
        pref_title.set_markup(f"<b>{GLib.markup_escape_text(self.i18n.t('wizard_pref_title'))}</b>")
        card_pref.pack_start(pref_title, False, False, 0)

        # Auto-send switch
        as_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        as_lbl = Gtk.Label(label=self.i18n.t("wizard_lbl_autosend"), xalign=0)
        as_hbox.pack_start(as_lbl, True, True, 0)
        self.autosend_switch = Gtk.Switch()
        self.autosend_switch.set_active(self.config.get("auto_send", False))
        as_hbox.pack_end(self.autosend_switch, False, False, 0)
        card_pref.pack_start(as_hbox, False, False, 2)

        # Auto-pause media
        ap_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        ap_lbl = Gtk.Label(label=self.i18n.t("wizard_lbl_autopause"), xalign=0)
        ap_hbox.pack_start(ap_lbl, True, True, 0)
        self.autopause_switch = Gtk.Switch()
        self.autopause_switch.set_active(self.config.get("auto_pause_media", True))
        ap_hbox.pack_end(self.autopause_switch, False, False, 0)
        card_pref.pack_start(ap_hbox, False, False, 2)

        # Restore window focus
        rf_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        rf_lbl = Gtk.Label(label=self.i18n.t("wizard_lbl_restore_focus"), xalign=0)
        rf_hbox.pack_start(rf_lbl, True, True, 0)
        self.restore_focus_switch = Gtk.Switch()
        self.restore_focus_switch.set_active(self.config.get("restore_window_focus", False))
        rf_hbox.pack_end(self.restore_focus_switch, False, False, 0)
        card_pref.pack_start(rf_hbox, False, False, 2)

        # Check updates
        cu_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        cu_lbl = Gtk.Label(label=self.i18n.t("lbl_check_updates"), xalign=0)
        cu_hbox.pack_start(cu_lbl, True, True, 0)
        self.check_updates_switch = Gtk.Switch()
        self.check_updates_switch.set_active(self.config.get("check_updates", False))
        cu_hbox.pack_end(self.check_updates_switch, False, False, 0)
        card_pref.pack_start(cu_hbox, False, False, 2)

        # Update frequency
        uf_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        uf_lbl = Gtk.Label(label=self.i18n.t("lbl_update_frequency"), xalign=0)
        uf_lbl.set_margin_start(16)
        uf_lbl.get_style_context().add_class("row-subtitle")
        uf_hbox.pack_start(uf_lbl, True, True, 0)
        self.update_freq_combo = Gtk.ComboBoxText()
        self.update_freq_combo.append("daily", self.i18n.t("freq_daily"))
        self.update_freq_combo.append("weekly", self.i18n.t("freq_weekly"))
        self.update_freq_combo.append("monthly", self.i18n.t("freq_monthly"))
        self.update_freq_combo.set_active_id(self.config.get("update_frequency", "monthly"))
        self.update_freq_combo.set_sensitive(self.check_updates_switch.get_active())
        uf_hbox.pack_end(self.update_freq_combo, False, False, 0)
        card_pref.pack_start(uf_hbox, False, False, 2)
        
        def _on_cu_toggled(switch, gparam):
            self.update_freq_combo.set_sensitive(switch.get_active())
        self.check_updates_switch.connect("notify::active", _on_cu_toggled)

        box.pack_start(card_pref, False, False, 0)

        # Ready Banner
        card_done = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card_done.get_style_context().add_class("wizard-card")

        done_title = Gtk.Label(xalign=0)
        done_title.set_markup(f"<span size='large' weight='bold' foreground='#57e389'>{GLib.markup_escape_text(self.i18n.t('wizard_finish_title'))}</span>")
        card_done.pack_start(done_title, False, False, 0)

        done_desc = Gtk.Label(label=self.i18n.t("wizard_finish_subtitle"), xalign=0)
        done_desc.set_line_wrap(True)
        card_done.pack_start(done_desc, False, False, 0)

        box.pack_start(card_done, False, False, 0)
        self.stack.add_named(scroll, "step_7")

    # -------------------------------------------------------------------------
    # Actions & Step Navigation
    # -------------------------------------------------------------------------
    def _update_step_view(self) -> None:
        """Update breadcrumb indicators and button states according to current step."""
        self.stack.set_visible_child_name(f"step_{self.current_step}")
        self.btn_back.set_sensitive(self.current_step > 0)

        if self.current_step == self.total_steps - 1:
            self.btn_next.set_label(self.i18n.t("wizard_btn_finish"))
            self.btn_next.get_style_context().remove_class("btn-primary")
            self.btn_next.get_style_context().add_class("btn-finish")
        else:
            self.btn_next.set_label(self.i18n.t("wizard_btn_next"))
            self.btn_next.get_style_context().remove_class("btn-finish")
            self.btn_next.get_style_context().add_class("btn-primary")

        for i, lbl in enumerate(self.step_labels):
            ctx = lbl.get_style_context()
            ctx.remove_class("active")
            ctx.remove_class("completed")
            if i == self.current_step:
                ctx.add_class("active")
            elif i < self.current_step:
                ctx.add_class("completed")

    def _on_next_clicked(self, btn: Gtk.Button) -> None:
        """Advance to next wizard page or trigger save on final page.

        Args:
            btn: Button emitting the clicked signal.
        """
        if self.current_step < self.total_steps - 1:
            self.current_step += 1
            self._update_step_view()
        else:
            self._save_and_close()

    def _on_back_clicked(self, btn: Gtk.Button) -> None:
        """Return to previous wizard page.

        Args:
            btn: Button emitting the clicked signal.
        """
        if self.current_step > 0:
            self.current_step -= 1
            self._update_step_view()

    def _record_wizard_sample(self, action: str, btn: Gtk.Button) -> None:
        """Launch interactive sample recorder dialog in wizard."""
        from ui.sample_recorder import SampleRecorderDialog
        action_names = {
            "START": self.i18n.t("voice_cmd_start"),
            "SEND": self.i18n.t("voice_cmd_send"),
            "PAUSE": self.i18n.t("voice_cmd_pause"),
            "CANCEL": self.i18n.t("voice_cmd_cancel"),
        }
        name = action_names.get(action, action)
        phrases = self.voice_commands.get_phrases_for_action(action)
        first_phrase = phrases[0] if phrases else None

        def _on_saved():
            phs = self.voice_commands.get_phrases_for_action(action)
            cnt = sum(len(p.samples) for p in phs)
            if action in self.wizard_cmd_labels:
                self.wizard_cmd_labels[action].set_label(f"{cnt} muestra(s)")

        dialog = SampleRecorderDialog(
            parent=self,
            action=action,
            action_display_name=name,
            voice_commands=self.voice_commands,
            aec_manager=self.aec,
            phrase=first_phrase,
            ui_language=self.selected_lang,
            on_saved=_on_saved
        )
        dialog.show_all()

    def _clear_wizard_sample(self, action: str) -> None:
        """Clear templates for given action in wizard."""
        self.voice_commands.clear_templates(action)
        self.voice_commands.save_templates()
        if action in self.wizard_cmd_labels:
            self.wizard_cmd_labels[action].set_label("0 muestras")

    def _on_wizard_calibrate_aec(self, btn: Gtk.Button) -> None:
        """Run calibration in wizard."""
        import threading
        btn.set_sensitive(False)
        self.calib_res_lbl.set_label(self.i18n.t("calibrating"))

        def _worker():
            calibrator = AcousticCalibrator()
            res = calibrator.run_calibration()

            def _done():
                btn.set_sensitive(True)
                self.calib_res_lbl.set_label(res.message)
                return False

            GLib.idle_add(_done)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_wizard_calibrate_noise(self, btn: Gtk.Button) -> None:
        """Run 2-second ambient silence calibration in wizard."""
        import threading, subprocess, time, socket, logging, numpy as np
        from core.ipc import SOCKET_PATH
        btn.set_sensitive(False)
        self.wizard_noise_lbl.set_label("⏳ Calibrando silencio...")

        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(SOCKET_PATH)
            s.sendall(b"pause-voice-listener")
            s.close()
        except Exception:
            pass

        def _worker():
            dev = self.aec.get_preferred_capture_device()
            cmd = ["arecord", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", "16000"]
            if dev and dev != "default":
                cmd.extend(["-D", dev])

            samples_list = []
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                t_end = time.time() + 2.0
                while time.time() < t_end and proc and proc.stdout:
                    chunk = proc.stdout.read(1024)
                    if not chunk:
                        break
                    pcm = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                    rms = float(np.sqrt(np.mean(pcm ** 2)))
                    samples_list.append(rms)
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception as e:
                logging.error(f"Wizard noise calibration capture error: {e}")

            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(0.5)
                s.connect(SOCKET_PATH)
                s.sendall(b"resume-voice-listener")
                s.close()
            except Exception:
                pass

            def _done():
                btn.set_sensitive(True)
                if samples_list:
                    mean_floor = float(np.mean(samples_list))
                    std_floor = float(np.std(samples_list))
                    max_floor = float(np.max(samples_list))

                    opt_th = max(mean_floor * 2.2, max_floor + 2.5 * std_floor, 0.015)
                    opt_th = round(opt_th, 3)
                    mean_floor = round(mean_floor, 3)

                    self.config["voice_vad_noise_floor"] = mean_floor
                    self.config["voice_vad_threshold"] = opt_th
                    self.voice_commands.config = self.config
                    self.wizard_noise_lbl.set_label(f"✅ Piso: {mean_floor:.3f} | Umbral: {opt_th:.3f}")
                else:
                    self.wizard_noise_lbl.set_label("⚠️ Error de captura")
                return False

            GLib.idle_add(_done)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_install_opendeck_in_wizard(self, btn: Gtk.Button) -> None:
        """Install Stream Deck / OpenDeck plugin from wizard interface.

        Args:
            btn: Install button widget.
        """
        opendeck_plugins_dir = os.path.expanduser("~/.config/opendeck/plugins/")
        plugin_name = "com.kirulab.opendictate.sdplugin"
        target_dir = os.path.join(opendeck_plugins_dir, plugin_name)
        source_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins", plugin_name)

        try:
            os.makedirs(opendeck_plugins_dir, exist_ok=True)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            if os.path.exists(source_dir):
                shutil.copytree(source_dir, target_dir)
                dlg = Gtk.MessageDialog(
                    transient_for=self,
                    flags=0,
                    message_type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    text=self.i18n.t("wizard_opendeck_installed_dialog")
                )
                dlg.run()
                dlg.destroy()
                btn.set_label(self.i18n.t("wizard_plugin_installed_btn"))
                btn.set_sensitive(False)
        except Exception as e:
            btn.set_label(f"Error: {e}")

    def _save_and_close(self) -> None:
        """Persist all selected preferences, mark onboarding complete, and close window."""
        # Save Model
        if hasattr(self, 'model_combo'):
            selected_model = self.model_combo.get_active_id() or "small"
            self.config["whisper_model_size"] = selected_model

        # Save Desktop Integration
        if hasattr(self, 'radio_gnome') and self.radio_gnome.get_active():
            self.config["indicator_mode"] = "gnome_ext"
            self.config["use_gnome_ext"] = True
            self.config["use_appindicator"] = False
            subprocess.Popen(["gnome-extensions", "enable", "com.kirulab.opendictate@kirulab.com"])
        else:
            self.config["indicator_mode"] = "tray"
            self.config["use_gnome_ext"] = False
            self.config["use_appindicator"] = True
            subprocess.Popen(["gnome-extensions", "disable", "com.kirulab.opendictate@kirulab.com"])

        # Save Bubble Mode & Text Collapse State
        if self.selected_bubble_mode == "text":
            self.config["bubble_mode"] = "text"
            self.config["hide_bubble"] = False
            self.config["bubble_text_collapsed"] = False
        elif self.selected_bubble_mode == "interactive":
            self.config["bubble_mode"] = "interactive"
            self.config["hide_bubble"] = False
            self.config["bubble_text_collapsed"] = False
        elif self.selected_bubble_mode == "compact":
            self.config["bubble_mode"] = "interactive"
            self.config["hide_bubble"] = False
            self.config["bubble_text_collapsed"] = True
        elif self.selected_bubble_mode == "none":
            self.config["hide_bubble"] = True
            self.config["bubble_mode"] = "auto"

        # Save Voice Commands
        if hasattr(self, 'sw_voice'):
            self.config["voice_commands_enabled"] = self.sw_voice.get_active()
        self.voice_commands.save_templates()

        # Save AI Settings
        if hasattr(self, 'stt_backend_combo'):
            self.config["stt_backend"] = self.stt_backend_combo.get_active_id() or "local_whisper"

        if hasattr(self, 'ai_enable_switch'):
            is_ai_on = self.ai_enable_switch.get_active()
            self.config["ai_enabled"] = is_ai_on
            self.config["llm_enabled"] = is_ai_on

        if hasattr(self, 'api_key_entry'):
            api_key = self.api_key_entry.get_text().strip()
            self.config["api_key"] = api_key

        if hasattr(self, 'ai_model_combo'):
            entry_child = self.ai_model_combo.get_child()
            model_val = entry_child.get_text().strip() if entry_child else "gemini-3.1-flash-live-preview"
            self.config["model"] = model_val or "gemini-3.1-flash-live-preview"

        # Save Preferences
        if hasattr(self, 'autostart_switch'):
            self._save_autostart()
        if hasattr(self, 'autosend_switch'):
            self.config["auto_send"] = self.autosend_switch.get_active()
        if hasattr(self, 'autopause_switch'):
            self.config["auto_pause_media"] = self.autopause_switch.get_active()
        if hasattr(self, 'restore_focus_switch'):
            self.config["restore_window_focus"] = self.restore_focus_switch.get_active()
        if hasattr(self, 'check_updates_switch'):
            self.config["check_updates"] = self.check_updates_switch.get_active()
        if hasattr(self, 'update_freq_combo'):
            self.config["update_frequency"] = self.update_freq_combo.get_active_id() or "monthly"

        self.config["ui_language"] = self.selected_lang
        self.config["initial_setup_completed"] = True

        if self.config_manager:
            self.config_manager.save_config(self.config)

        if self.on_finish:
            self.on_finish(self.config)

        self.destroy()

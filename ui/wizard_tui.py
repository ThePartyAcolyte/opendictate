"""
Terminal User Interface (TUI) Onboarding Wizard for OpenDictate.

Step-by-step first run configuration:
1. Interface Language
2. Hardware Detection & Whisper Model selection
3. Desktop Integration (Omarchy Shell / GNOME / Tray)
4. AI Cleanup (Optional Gemini API key)
5. Global Shortcuts & Completion
"""

import os
import shutil
import socket
import subprocess
import threading
from typing import Dict, Any, List

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Header,
    Footer,
    TabbedContent,
    TabPane,
    Switch,
    Select,
    Input,
    Button,
    Label,
    Static,
    Rule,
)
from textual.binding import Binding

from core.config import ConfigManager, CONFIG_PATH
from core.ipc import SOCKET_PATH
from core.hardware import get_system_hardware_info
from i18n.translator import get_translator


WHISPER_MODELS = [
    ("small (244 MB - Recomendado)", "small"),
    ("base (74 MB - Rápido)", "base"),
    ("tiny (39 MB - Ultraligero)", "tiny"),
    ("medium (769 MB - Alta precisión)", "medium"),
    ("large-v3-turbo (809 MB)", "large-v3-turbo"),
]

LANGUAGES = [
    ("Español", "es"),
    ("English", "en"),
    ("Deutsch", "de"),
    ("Français", "fr"),
]

GEMINI_MODELS = [
    ("Gemma 4 26B (Recomendado)", "gemma-4-26b-a4b-it"),
    ("Gemini 2.5 Flash", "gemini-2.5-flash"),
    ("Gemini 2.0 Flash", "gemini-2.0-flash"),
]


def get_omarchy_palette() -> Dict[str, str]:
    """Extract semantic color palette from active Omarchy theme."""
    palette = {
        "bg": "#0c0b0c",
        "fg": "#FAFCFB",
        "accent": "#b59790",
        "primary": "#b59790",
        "secondary": "#a5a0b6",
        "surface": "#161416",
        "panel": "#201c21",
        "border": "#584e51",
        "error": "#c38b7b",
        "success": "#87a9b0",
        "warning": "#6B5E73",
        "muted": "#8a8588",
    }
    try:
        res = subprocess.run(
            ["omarchy", "theme", "color", "--all"],
            capture_output=True,
            text=True,
            timeout=0.8
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                parts = line.strip().split("\t")
                if len(parts) == 2:
                    k, v = parts[0].strip(), parts[1].strip()
                    if k in ("bg", "background"):
                        palette["bg"] = v
                    elif k in ("fg", "foreground"):
                        palette["fg"] = v
                    elif k == "accent":
                        palette["accent"] = v
                        palette["primary"] = v
                    elif k in ("cyan", "bright_cyan"):
                        palette["secondary"] = v
                    elif k in ("selection", "selection_background"):
                        palette["panel"] = v
                    elif k in ("lighter_bg", "lighter_background"):
                        palette["surface"] = v
                    elif k in ("red", "color1"):
                        palette["error"] = v
                    elif k in ("green", "color2"):
                        palette["success"] = v
                    elif k in ("yellow", "color3"):
                        palette["warning"] = v
                    elif k == "muted":
                        palette["muted"] = v
                        palette["border"] = v
    except Exception:
        pass
    return palette


PALETTE = get_omarchy_palette()

WIZARD_CSS = f"""
Screen {{
    background: {PALETTE['bg']};
    color: {PALETTE['fg']};
}}

Header {{
    background: {PALETTE['surface']};
    color: {PALETTE['accent']};
}}

Footer {{
    background: {PALETTE['surface']};
    color: {PALETTE['fg']};
}}

.wizard-container {{
    padding: 1 2;
    height: 1fr;
}}

.step-title {{
    text-style: bold;
    color: {PALETTE['accent']};
    font-size: 16;
    margin-bottom: 1;
}}

.step-desc {{
    color: {PALETTE['muted']};
    margin-bottom: 1;
}}

.card-box {{
    border: round {PALETTE['border']};
    padding: 1;
    margin-bottom: 1;
    background: {PALETTE['surface']};
}}

.field-row {{
    height: auto;
    margin-bottom: 1;
    align-vertical: middle;
}}

.field-label {{
    width: 32;
    text-style: bold;
    color: {PALETTE['fg']};
}}

.footer-bar {{
    dock: bottom;
    height: 3;
    padding: 0 2;
    background: {PALETTE['surface']};
    align: right middle;
    border-top: solid {PALETTE['border']};
}}

.btn-action {{
    margin-left: 1;
}}

.btn-primary {{
    background: {PALETTE['primary']};
    color: {PALETTE['bg']};
    text-style: bold;
}}

.btn-success {{
    background: {PALETTE['success']};
    color: {PALETTE['bg']};
    text-style: bold;
}}

Input, Select {{
    background: {PALETTE['panel']};
    color: {PALETTE['fg']};
    border: tall {PALETTE['border']};
}}

Input:focus, Select:focus {{
    border: tall {PALETTE['accent']};
}}

Switch {{
    background: {PALETTE['panel']};
}}
"""


class WizardTUI(App):
    """Modern terminal onboarding wizard for OpenDictate."""

    TITLE = "Asistente Inicial - OpenDictate"
    CSS = WIZARD_CSS

    BINDINGS = [
        Binding("ctrl+q", "quit_wizard", "Salir", show=False),
        Binding("escape", "quit_wizard", "Salir", show=True),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cm = ConfigManager()
        self.cfg = self.cm.load_config()
        self.hw_info = get_system_hardware_info()
        self.current_step = 0
        self.total_steps = 5

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(classes="wizard-container"):
            with TabbedContent(initial="step_0", id="wizard_tabs"):
                # Step 1: Idioma
                with TabPane("1. Idioma", id="step_0"):
                    with VerticalScroll():
                        yield Label("Bienvenido a OpenDictate", classes="step-title")
                        yield Label(
                            "Selecciona el idioma principal para la interfaz de usuario.",
                            classes="step-desc"
                        )
                        with Vertical(classes="card-box"):
                            with Horizontal(classes="field-row"):
                                yield Label("Idioma de Interfaz:", classes="field-label")
                                yield Select(
                                    options=LANGUAGES,
                                    value=self.cfg.get("ui_language", "es"),
                                    id="sel_lang"
                                )

                # Step 2: Hardware y Modelo
                with TabPane("2. Hardware y Modelo", id="step_1"):
                    with VerticalScroll():
                        yield Label("Detección de Hardware y Modelo STT", classes="step-title")

                        gpu_text = f"GPU: {self.hw_info.get('gpu_name', 'No detectada')} | CUDA: {'Disponible' if self.hw_info.get('has_cuda') else 'No'}"
                        yield Static(f"Diagnóstico del Sistema:\n• {gpu_text}\n• CPU Threads: {os.cpu_count() or 4}", classes="card-box")

                        with Vertical(classes="card-box"):
                            with Horizontal(classes="field-row"):
                                yield Label("Modelo Whisper:", classes="field-label")
                                yield Select(
                                    options=WHISPER_MODELS,
                                    value=self.cfg.get("whisper_model_size", "small"),
                                    id="sel_model"
                                )
                            yield Label("", id="model_download_status")
                            yield Button("Descargar Modelo Ahora", id="btn_dl_wizard", variant="primary", classes="btn-action")

                # Step 3: Integración de Escritorio
                with TabPane("3. Integración", id="step_2"):
                    with VerticalScroll():
                        yield Label("Integración con el Entorno de Escritorio", classes="step-title")

                        is_omarchy = os.path.exists(os.path.expanduser("~/.config/omarchy")) or bool(shutil.which("omarchy-shell"))
                        if is_omarchy:
                            yield Static(
                                "🪄 Entorno Omarchy Detectado:\n"
                                "El plugin de barra para Omarchy Shell (com.kirulab.opendictate) se encuentra instalado "
                                "y configurado en tu barra superior.\n\n"
                                "• Muestra onda de audio en vivo, cronómetro y botones interactivos.\n"
                                "• Actúa como el HUD principal en Wayland sin interferir con ventanas.",
                                classes="card-box"
                            )
                        else:
                            yield Static(
                                "Elige cómo visualizar OpenDictate en tu escritorio:\n"
                                "• Bandeja del sistema (AppIndicator) para escritorios estándar.\n"
                                "• Extensión para GNOME Shell si utilizas GNOME.",
                                classes="card-box"
                            )

                # Step 4: Limpieza con IA (Opcional)
                with TabPane("4. IA (Opcional)", id="step_3"):
                    with VerticalScroll():
                        yield Label("Limpieza y Corrección con IA", classes="step-title")
                        yield Label(
                            "OpenDictate puede corregir gramática, puntuación y estilo en tiempo real usando Gemini o Gemma.",
                            classes="step-desc"
                        )

                        with Vertical(classes="card-box"):
                            with Horizontal(classes="field-row"):
                                yield Label("Habilitar Limpieza con IA:", classes="field-label")
                                yield Switch(value=bool(self.cfg.get("ai_enabled", False)), id="sw_wiz_ai")

                            with Horizontal(classes="field-row"):
                                yield Label("Modelo:", classes="field-label")
                                yield Select(
                                    options=GEMINI_MODELS,
                                    value=self.cfg.get("model", "gemma-4-26b-a4b-it"),
                                    id="sel_wiz_gemini"
                                )

                            with Horizontal(classes="field-row"):
                                yield Label("Clave API de Gemini:", classes="field-label")
                                yield Input(
                                    value=self.cfg.get("api_key", ""),
                                    password=True,
                                    placeholder="Introduce clave API (o déjalo en blanco para configurar luego)",
                                    id="inp_wiz_api_key"
                                )

                # Step 5: Atajos y Finalización
                with TabPane("5. Finalizar", id="step_4"):
                    with VerticalScroll():
                        yield Label("¡Todo Listo para Dictar!", classes="step-title")
                        yield Static(
                            "Para asignar un atajo global de dictado en Hyprland / Omarchy, añade a ~/.config/hypr/bindings.lua:\n\n"
                            "  bind = $mainMod, D, exec, opendictate --toggle-record-send\n\n"
                            "También puedes activar el dictado haciendo click en el icono de micrófono de tu barra.",
                            classes="card-box"
                        )

        with Horizontal(classes="footer-bar"):
            yield Label("", id="nav_status")
            yield Button("Anterior", id="btn_prev", classes="btn-action")
            yield Button("Siguiente", id="btn_next", variant="primary", classes="btn-action")

        yield Footer()

    def on_mount(self) -> None:
        self.update_nav_buttons()
        self.check_initial_model_status()

    def check_initial_model_status(self) -> None:
        sel_model = self.query_one("#sel_model", Select).value or "small"
        hf_path = os.path.expanduser(f"~/.cache/huggingface/hub/models--Systran--faster-whisper-{sel_model}")
        status_lbl = self.query_one("#model_download_status", Label)
        if os.path.exists(hf_path):
            status_lbl.update(f"✔ El modelo '{sel_model}' ya se encuentra descargado en disco.")
        else:
            status_lbl.update(f"○ El modelo '{sel_model}' no está descargado aún.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn_next":
            self.go_next()
        elif btn_id == "btn_prev":
            self.go_prev()
        elif btn_id == "btn_dl_wizard":
            self.download_model()

    def download_model(self) -> None:
        sel_model = self.query_one("#sel_model", Select).value or "small"
        status_lbl = self.query_one("#model_download_status", Label)
        status_lbl.update(f"Descargando modelo '{sel_model}' en segundo plano...")

        def _do_dl():
            try:
                from faster_whisper import download_model
                download_model(sel_model)
                self.call_from_thread(self._on_dl_ok, sel_model)
            except Exception as e:
                self.call_from_thread(self._on_dl_err, str(e))

        threading.Thread(target=_do_dl, daemon=True).start()

    def _on_dl_ok(self, model_name: str) -> None:
        status_lbl = self.query_one("#model_download_status", Label)
        status_lbl.update(f"✔ Modelo '{model_name}' descargado correctamente.")

    def _on_dl_err(self, err: str) -> None:
        status_lbl = self.query_one("#model_download_status", Label)
        status_lbl.update(f"❌ Error al descargar: {err}")

    def update_nav_buttons(self) -> None:
        btn_prev = self.query_one("#btn_prev", Button)
        btn_next = self.query_one("#btn_next", Button)

        btn_prev.disabled = (self.current_step == 0)

        if self.current_step == self.total_steps - 1:
            btn_next.label = "Finalizar"
            btn_next.variant = "success"
        else:
            btn_next.label = "Siguiente"
            btn_next.variant = "primary"

    def go_next(self) -> None:
        if self.current_step < self.total_steps - 1:
            self.current_step += 1
            tabs = self.query_one("#wizard_tabs", TabbedContent)
            tabs.active = f"step_{self.current_step}"
            self.update_nav_buttons()
        else:
            self.save_and_finish()

    def go_prev(self) -> None:
        if self.current_step > 0:
            self.current_step -= 1
            tabs = self.query_one("#wizard_tabs", TabbedContent)
            tabs.active = f"step_{self.current_step}"
            self.update_nav_buttons()

    def save_and_finish(self) -> None:
        # Collect values
        self.cfg["ui_language"] = self.query_one("#sel_lang", Select).value
        self.cfg["whisper_model_size"] = self.query_one("#sel_model", Select).value
        self.cfg["ai_enabled"] = self.query_one("#sw_wiz_ai", Switch).value
        self.cfg["model"] = self.query_one("#sel_wiz_gemini", Select).value
        self.cfg["api_key"] = self.query_one("#inp_wiz_api_key", Input).value.strip()

        # Desktop mode
        is_omarchy = os.path.exists(os.path.expanduser("~/.config/omarchy")) or bool(shutil.which("omarchy-shell"))
        if is_omarchy:
            self.cfg["indicator_mode"] = "omarchy"
            self.cfg["use_gnome_ext"] = False
            self.cfg["use_appindicator"] = False
            self.cfg["hide_bubble"] = True

        self.cfg["initial_setup_completed"] = True
        self.cm.save_config(self.cfg, explicit_api_key_update=True)

        # Signal daemon
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(SOCKET_PATH)
            s.sendall(b"reload-config")
            s.close()
        except Exception:
            pass

        self.exit()

    def action_quit_wizard(self) -> None:
        self.exit()


def run_wizard() -> None:
    """Launch the onboarding TUI wizard."""
    app = WizardTUI()
    app.run()


if __name__ == "__main__":
    run_wizard()

"""
Terminal User Interface (TUI) for OpenDictate Settings.

Full feature parity with GTK settings:
- STT & Whisper Model Management (Activate, Download, Delete, Acceleration parameters)
- AI Post-Processing & Cleanup (Gemini / Gemma, API Key tester, Custom System Prompts)
- Audio & VAD (Real-time streaming, AEC, Live Microphone Level Tester)
- Voice Commands (Thresholds, Silence pauses, Recognized commands)
- General & Multimedia (Language, Auto-send, Window focus, MPRIS media control)
- CLI Shortcuts & Integrations (One-click clipboard copy, Hyprland bindings)
- Dynamic Omarchy Theme integration matching active desktop palette
"""

import os
import shutil
import socket
import struct
import math
import subprocess
import threading
import time
from typing import Dict, Any, List, Optional, Tuple

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
    TextArea,
    Button,
    Label,
    Static,
    Rule,
    ProgressBar,
)
from textual.binding import Binding

from core.config import ConfigManager, CONFIG_PATH, DEFAULT_CONFIG
from core.ipc import SOCKET_PATH
from i18n.translator import get_translator


WHISPER_MODELS = [
    ("tiny", "39 MB", "Ultraligero / CPU"),
    ("base", "74 MB", "Rápido / CPU o GPU"),
    ("small", "244 MB", "Balance ideal (Recomendado)"),
    ("medium", "769 MB", "Alta precisión / GPU"),
    ("large-v3", "1.5 GB", "Máxima precisión"),
    ("large-v3-turbo", "809 MB", "Rápido y preciso"),
]

GEMINI_MODELS = [
    ("Gemma 4 26B (Recomendado)", "gemma-4-26b-a4b-it"),
    ("Gemini 2.5 Flash", "gemini-2.5-flash"),
    ("Gemini 2.5 Pro", "gemini-2.5-pro"),
    ("Gemini 2.0 Flash", "gemini-2.0-flash"),
]

STT_BACKENDS = [
    ("Local Whisper (Faster-Whisper)", "local_whisper"),
    ("Gemini Live (Streaming Cloud)", "gemini_live"),
]

DEVICES = [
    ("Automático (Detectar CUDA / CPU)", "auto"),
    ("NVIDIA CUDA (GPU)", "cuda"),
    ("CPU", "cpu"),
]

COMPUTE_TYPES = [
    ("Default (Recomendado)", "default"),
    ("Float16 (GPU Rápida)", "float16"),
    ("Int8 Float16 (Balanceado)", "int8_float16"),
    ("Int8 (CPU / Bajo consumo)", "int8"),
]

THINKING_LEVELS = [
    ("Mínimo (Rápido)", "minimal"),
    ("Bajo", "low"),
    ("Medio", "medium"),
    ("Alto (Profundo)", "high"),
]

LANGUAGES = [
    ("Español", "es"),
    ("English", "en"),
    ("Deutsch", "de"),
    ("Français", "fr"),
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

SETTINGS_CSS = f"""
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

TabbedContent {{
    height: 1fr;
}}

TabPane {{
    padding: 1 2;
}}

.section-title {{
    text-style: bold;
    color: {PALETTE['accent']};
    margin-top: 1;
    margin-bottom: 1;
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

.field-desc {{
    color: {PALETTE['muted']};
    margin-bottom: 1;
}}

.card-box {{
    border: round {PALETTE['border']};
    padding: 1;
    margin-bottom: 1;
    background: {PALETTE['surface']};
}}

.action-bar {{
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

.btn-danger {{
    background: {PALETTE['error']};
    color: {PALETTE['bg']};
    text-style: bold;
}}

.status-badge {{
    padding: 0 1;
    margin-top: 1;
    margin-bottom: 1;
}}

Input, Select, TextArea {{
    background: {PALETTE['panel']};
    color: {PALETTE['fg']};
    border: tall {PALETTE['border']};
}}

Input:focus, Select:focus, TextArea:focus {{
    border: tall {PALETTE['accent']};
}}

Switch {{
    background: {PALETTE['panel']};
}}

.shortcut-row {{
    height: auto;
    margin-bottom: 1;
    padding: 0 1;
    align-vertical: middle;
}}

.shortcut-cmd {{
    width: 1fr;
    color: {PALETTE['secondary']};
    text-style: bold;
}}
"""


def copy_to_clipboard(text: str) -> bool:
    """Copy text to Wayland or X11 clipboard."""
    try:
        if shutil.which("wl-copy"):
            subprocess.run(["wl-copy"], input=text, text=True, timeout=1.0)
            return True
        elif shutil.which("xclip"):
            subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, timeout=1.0)
            return True
    except Exception:
        pass
    return False


class SettingsTUI(App):
    """Modern terminal configuration interface for OpenDictate."""

    TITLE = "Ajustes - OpenDictate"
    CSS = SETTINGS_CSS

    BINDINGS = [
        Binding("ctrl+s", "save_and_apply", "Guardar y Aplicar", show=True),
        Binding("escape", "quit_app", "Salir", show=True),
        Binding("ctrl+q", "quit_app", "Salir", show=False),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cm = ConfigManager()
        self.cfg = self.cm.load_config()
        self.i18n = get_translator(self.cfg.get("ui_language", "es"))
        self.api_key_hidden = True
        self.testing_mic = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="tab_models"):
            # 1. STT & Whisper Models
            with TabPane("Modelos y STT", id="tab_models"):
                with VerticalScroll():
                    yield Label("Motor de Reconocimiento de Voz (STT)", classes="section-title")
                    with Vertical(classes="card-box"):
                        with Horizontal(classes="field-row"):
                            yield Label("Backend STT:", classes="field-label")
                            yield Select(
                                options=STT_BACKENDS,
                                value=self.cfg.get("stt_backend", "local_whisper"),
                                id="sel_backend"
                            )

                        with Horizontal(classes="field-row"):
                            yield Label("Modelo Activo:", classes="field-label")
                            yield Select(
                                options=[(f"{name} ({size} - {desc})", name) for name, size, desc in WHISPER_MODELS],
                                value=self.cfg.get("whisper_model_size", "small"),
                                id="sel_active_model"
                            )

                    yield Label("Modelos en Disco (Caché Local)", classes="section-title")
                    with Vertical(classes="card-box"):
                        yield Static(id="models_status_view")
                        yield Label("", id="model_action_feedback")
                        with Horizontal(classes="field-row"):
                            yield Button("Activar Seleccionado", id="btn_activate_model", variant="primary", classes="btn-action")
                            yield Button("Descargar Modelo", id="btn_download_model", variant="success", classes="btn-action")
                            yield Button("Eliminar de Disco", id="btn_delete_model", variant="error", classes="btn-action")

                    yield Label("Aceleración y Recursos de Cómputo", classes="section-title")
                    with Vertical(classes="card-box"):
                        with Horizontal(classes="field-row"):
                            yield Label("Dispositivo:", classes="field-label")
                            yield Select(
                                options=DEVICES,
                                value=self.cfg.get("whisper_device", "auto"),
                                id="sel_device"
                            )

                        with Horizontal(classes="field-row"):
                            yield Label("Tipo de Cómputo:", classes="field-label")
                            yield Select(
                                options=COMPUTE_TYPES,
                                value=self.cfg.get("whisper_compute_type", "default"),
                                id="sel_compute"
                            )

                        with Horizontal(classes="field-row"):
                            yield Label("Hilos CPU (0 = auto):", classes="field-label")
                            yield Input(
                                value=str(self.cfg.get("whisper_cpu_threads", 0)),
                                id="inp_threads",
                                placeholder="0"
                            )

            # 2. AI Post-Processing
            with TabPane("Limpieza con IA", id="tab_ai"):
                with VerticalScroll():
                    yield Label("Post-Procesamiento Inteligente con LLM", classes="section-title")
                    with Vertical(classes="card-box"):
                        with Horizontal(classes="field-row"):
                            yield Label("Habilitar Limpieza con IA:", classes="field-label")
                            yield Switch(value=bool(self.cfg.get("ai_enabled", False)), id="sw_ai")

                        with Horizontal(classes="field-row"):
                            yield Label("Modelo Gemini / Gemma:", classes="field-label")
                            yield Select(
                                options=GEMINI_MODELS,
                                value=self.cfg.get("model", "gemma-4-26b-a4b-it"),
                                id="sel_gemini_model"
                            )

                        with Horizontal(classes="field-row"):
                            yield Label("Clave API de Gemini:", classes="field-label")
                            yield Input(
                                value=self.cfg.get("api_key", ""),
                                password=True,
                                id="inp_api_key",
                                placeholder="Introduce tu clave API de Google AI Studio"
                            )

                        with Horizontal(classes="field-row"):
                            yield Button("Mostrar Clave", id="btn_toggle_key_vis", classes="btn-action")
                            yield Button("Probar Conexión API", id="btn_test_api", variant="primary", classes="btn-action")

                        yield Label("", id="api_test_feedback")

                        with Horizontal(classes="field-row"):
                            yield Label("Nivel de Razonamiento:", classes="field-label")
                            yield Select(
                                options=THINKING_LEVELS,
                                value=self.cfg.get("llm_thinking_level", "minimal"),
                                id="sel_thinking"
                            )

                    yield Label("Instrucciones Personalizadas (Prompt del Sistema)", classes="section-title")
                    with Vertical(classes="card-box"):
                        yield Label("Instrucciones adicionales para el modelo de IA:", classes="field-desc")
                        yield TextArea(
                            text=self.cfg.get("system_prompt", ""),
                            id="txt_system_prompt",
                            language="markdown"
                        )

            # 3. Audio & VAD
            with TabPane("Audio y VAD", id="tab_audio"):
                with VerticalScroll():
                    yield Label("Captura y Detección de Actividad de Voz (VAD)", classes="section-title")
                    with Vertical(classes="card-box"):
                        with Horizontal(classes="field-row"):
                            yield Label("Modo Tiempo Real (Chunks):", classes="field-label")
                            yield Switch(value=bool(self.cfg.get("realtime_mode", True)), id="sw_realtime")

                        with Horizontal(classes="field-row"):
                            yield Label("Cancelación de Eco (AEC):", classes="field-label")
                            yield Switch(value=bool(self.cfg.get("echo_cancellation_enabled", True)), id="sw_aec")

                        with Horizontal(classes="field-row"):
                            yield Label("Sensibilidad VAD (Energía):", classes="field-label")
                            yield Input(
                                value=str(self.cfg.get("chunk_vad_energy_threshold", 0.030)),
                                id="inp_vad_threshold"
                            )

                        with Horizontal(classes="field-row"):
                            yield Label("Silencio para corte (segundos):", classes="field-label")
                            yield Input(
                                value=str(self.cfg.get("chunk_silence_duration", 0.85)),
                                id="inp_silence_duration"
                            )

                        with Horizontal(classes="field-row"):
                            yield Label("Duración máxima fragmento (s):", classes="field-label")
                            yield Input(
                                value=str(self.cfg.get("chunk_max_duration", 30.0)),
                                id="inp_max_duration"
                            )

                    yield Label("Calibración y Prueba de Micrófono", classes="section-title")
                    with Vertical(classes="card-box"):
                        yield Static("Comprueba la intensidad de entrada de tu micrófono en tiempo real.", classes="field-desc")
                        yield Button("Probar Micrófono en Vivo (3s)", id="btn_test_mic", variant="primary")
                        yield Static(id="mic_test_meter")

            # 4. Voice Commands
            with TabPane("Comandos de Voz", id="tab_voice"):
                with VerticalScroll():
                    yield Label("Detección de Palabras Clave en Silencio", classes="section-title")
                    with Vertical(classes="card-box"):
                        with Horizontal(classes="field-row"):
                            yield Label("Habilitar Comandos de Voz:", classes="field-label")
                            yield Switch(value=bool(self.cfg.get("voice_commands_enabled", False)), id="sw_voice")

                        with Horizontal(classes="field-row"):
                            yield Label("Umbral de Coincidencia (0.5 - 1.0):", classes="field-label")
                            yield Input(
                                value=str(self.cfg.get("voice_command_threshold", 0.70)),
                                id="inp_voice_threshold"
                            )

                        with Horizontal(classes="field-row"):
                            yield Label("Pausa de silencio (segundos):", classes="field-label")
                            yield Input(
                                value=str(self.cfg.get("voice_command_silence_pause", 1.5)),
                                id="inp_voice_silence"
                            )

                    yield Label("Comandos Nativos Disponibles", classes="section-title")
                    with Vertical(classes="card-box"):
                        yield Static(
                            "• 'Enviar' / 'Send' -> Finaliza el dictado y envía el texto.\n"
                            "• 'Pausar' / 'Pause' -> Pausa temporalmente la grabación.\n"
                            "• 'Cancelar' / 'Cancel' -> Cancela y descarta el audio actual.",
                            classes="field-desc"
                        )

            # 5. General & Multimedia
            with TabPane("General", id="tab_general"):
                with VerticalScroll():
                    yield Label("Preferencias del Sistema y Comportamiento", classes="section-title")
                    with Vertical(classes="card-box"):
                        with Horizontal(classes="field-row"):
                            yield Label("Idioma de la Interfaz:", classes="field-label")
                            yield Select(
                                options=LANGUAGES,
                                value=self.cfg.get("ui_language", "es"),
                                id="sel_language"
                            )

                        with Horizontal(classes="field-row"):
                            yield Label("Enviar automático (Enter):", classes="field-label")
                            yield Switch(value=bool(self.cfg.get("auto_send", False)), id="sw_autosend")

                        with Horizontal(classes="field-row"):
                            yield Label("Restaurar foco de ventana:", classes="field-label")
                            yield Switch(value=bool(self.cfg.get("restore_window_focus", True)), id="sw_focus")

                        with Horizontal(classes="field-row"):
                            yield Label("Pausar multimedia (MPRIS):", classes="field-label")
                            yield Switch(value=bool(self.cfg.get("pause_media", True)), id="sw_mpris")

                        with Horizontal(classes="field-row"):
                            yield Label("Ocultar burbuja flotante:", classes="field-label")
                            yield Switch(value=bool(self.cfg.get("hide_bubble", True)), id="sw_hide_bubble")

            # 6. Shortcuts & Integrations
            with TabPane("Atajos y CLI", id="tab_shortcuts"):
                with VerticalScroll():
                    yield Label("Integración con Hyprland / Omarchy", classes="section-title")
                    with Vertical(classes="card-box"):
                        yield Static(
                            "Atajo global recomendado para ~/.config/hypr/bindings.lua:\n"
                            "  bind = $mainMod, D, exec, opendictate --toggle-record-send",
                            classes="field-desc"
                        )
                        yield Button("Copiar Atajo de Hyprland", id="btn_copy_hypr_binding", variant="primary")

                    yield Label("Comandos CLI Rápidos", classes="section-title")
                    with Vertical(classes="card-box"):
                        shortcuts = [
                            ("opendictate --toggle-record-send", "Alternar grabación / envío"),
                            ("opendictate --finish-normal", "Enviar sin procesamiento IA"),
                            ("opendictate --finish-ai", "Enviar forzando limpieza IA"),
                            ("opendictate --pause", "Pausar / Reanudar grabación"),
                            ("opendictate --cancel", "Cancelar y descartar audio"),
                            ("opendictate --toggle-ai", "Alternar Limpieza con IA"),
                            ("opendictate --toggle-autosend", "Alternar Enviar con Enter"),
                            ("opendictate --settings", "Abrir este panel de Ajustes"),
                        ]
                        for cmd, desc in shortcuts:
                            with Horizontal(classes="shortcut-row"):
                                yield Label(f"{cmd:<36} ({desc})", classes="shortcut-cmd")
                                yield Button("Copiar", id=f"btn_copy_{cmd.replace(' ', '_').replace('-', '_')}", classes="btn-action")

            # 7. Updates
            with TabPane("Actualizaciones", id="tab_updates"):
                with VerticalScroll():
                    yield Label("Gestión de Versiones", classes="section-title")
                    with Vertical(classes="card-box"):
                        yield Static("Versión instalada: v1.4.0 (Desarrollo Omarchy / Wayland)", classes="field-desc")
                        yield Button("Buscar Actualizaciones Ahora", id="btn_check_updates", variant="primary")
                        yield Label("", id="update_feedback")

        with Horizontal(classes="action-bar"):
            yield Label("", id="status_msg")
            yield Button("Restablecer", id="btn_reset", variant="default", classes="btn-action")
            yield Button("Guardar y Aplicar", id="btn_save", variant="success", classes="btn-action")
            yield Button("Salir", id="btn_quit", classes="btn-action")

        yield Footer()

    def on_mount(self) -> None:
        self.update_models_status()

    def update_models_status(self) -> None:
        """Scan HuggingFace cache and render downloaded models summary."""
        lines = []
        for name, size, desc in WHISPER_MODELS:
            hf_path = os.path.expanduser(f"~/.cache/huggingface/hub/models--Systran--faster-whisper-{name}")
            downloaded = os.path.exists(hf_path)
            is_active = (name == self.cfg.get("whisper_model_size", "small"))

            prefix = "● [ACTIVO]" if is_active else ("✔" if downloaded else "○")
            status = "Descargado en disco" if downloaded else "No descargado"
            lines.append(f"  {prefix:<10} {name:<16} {size:<10} - {status} ({desc})")

        status_widget = self.query_one("#models_status_view", Static)
        status_widget.update("\n".join(lines))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""

        if btn_id == "btn_save":
            self.action_save_and_apply()
        elif btn_id == "btn_quit":
            self.action_quit_app()
        elif btn_id == "btn_reset":
            self.reset_to_defaults()
        elif btn_id == "btn_activate_model":
            self.activate_selected_model()
        elif btn_id == "btn_download_model":
            self.download_selected_model()
        elif btn_id == "btn_delete_model":
            self.delete_selected_model()
        elif btn_id == "btn_toggle_key_vis":
            self.toggle_key_visibility()
        elif btn_id == "btn_test_api":
            self.test_api_connection()
        elif btn_id == "btn_test_mic":
            self.start_mic_level_test()
        elif btn_id == "btn_check_updates":
            self.check_updates_async()
        elif btn_id == "btn_copy_hypr_binding":
            copy_to_clipboard("bind = $mainMod, D, exec, opendictate --toggle-record-send")
            self.notify_user("✔ Atajo copiado al portapapeles")
        elif btn_id.startswith("btn_copy_"):
            cmd = btn_id.replace("btn_copy_", "").replace("_", "-").replace("opendictate-", "opendictate ")
            copy_to_clipboard(cmd)
            self.notify_user(f"✔ Copiado: {cmd}")

    def toggle_key_visibility(self) -> None:
        inp = self.query_one("#inp_api_key", Input)
        btn = self.query_one("#btn_toggle_key_vis", Button)
        self.api_key_hidden = not self.api_key_hidden
        inp.password = self.api_key_hidden
        btn.label = "Mostrar Clave" if self.api_key_hidden else "Ocultar Clave"

    def activate_selected_model(self) -> None:
        sel_widget = self.query_one("#sel_active_model", Select)
        model_name = sel_widget.value
        if model_name:
            self.cfg["whisper_model_size"] = model_name
            self.update_models_status()
            feedback = self.query_one("#model_action_feedback", Label)
            feedback.update(f"✔ Modelo '{model_name}' configurado como activo.")

    def download_selected_model(self) -> None:
        sel_widget = self.query_one("#sel_active_model", Select)
        model_name = sel_widget.value
        if not model_name:
            return

        feedback = self.query_one("#model_action_feedback", Label)
        feedback.update(f"Descargando modelo '{model_name}' desde HuggingFace...")

        def _do_download():
            try:
                from faster_whisper import download_model
                download_model(model_name)
                self.call_from_thread(self._on_download_complete, model_name)
            except Exception as e:
                self.call_from_thread(self._on_download_error, str(e))

        threading.Thread(target=_do_download, daemon=True).start()

    def _on_download_complete(self, model_name: str) -> None:
        self.update_models_status()
        feedback = self.query_one("#model_action_feedback", Label)
        feedback.update(f"✔ Modelo '{model_name}' descargado y verificado en caché local.")

    def _on_download_error(self, err: str) -> None:
        feedback = self.query_one("#model_action_feedback", Label)
        feedback.update(f"❌ Error al descargar: {err[:90]}")

    def delete_selected_model(self) -> None:
        sel_widget = self.query_one("#sel_active_model", Select)
        model_name = sel_widget.value
        hf_path = os.path.expanduser(f"~/.cache/huggingface/hub/models--Systran--faster-whisper-{model_name}")
        feedback = self.query_one("#model_action_feedback", Label)
        if os.path.exists(hf_path):
            try:
                shutil.rmtree(hf_path)
                self.update_models_status()
                feedback.update(f"✔ Modelo '{model_name}' eliminado de disco.")
            except Exception as e:
                feedback.update(f"❌ Error al eliminar: {e}")
        else:
            feedback.update(f"○ El modelo '{model_name}' no está presente en disco.")

    def test_api_connection(self) -> None:
        api_key = self.query_one("#inp_api_key", Input).value.strip()
        model_name = self.query_one("#sel_gemini_model", Select).value or "gemini-2.5-flash"
        feedback = self.query_one("#api_test_feedback", Label)

        if not api_key:
            feedback.update("⚠️ Por favor introduce una clave API antes de probar.")
            return

        feedback.update("Probando conexión con Google AI Studio...")

        def _do_test():
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                resp = client.models.generate_content(
                    model=model_name,
                    contents="Responde únicamente con la palabra OK",
                )
                if resp and resp.text:
                    self.call_from_thread(feedback.update, "✔ Conexión con Gemini API exitosa y validada.")
                else:
                    self.call_from_thread(feedback.update, "❌ No se recibió respuesta del modelo.")
            except Exception as e:
                self.call_from_thread(feedback.update, f"❌ Error de API: {str(e)[:80]}")

        threading.Thread(target=_do_test, daemon=True).start()

    def start_mic_level_test(self) -> None:
        if self.testing_mic:
            return
        self.testing_mic = True
        meter = self.query_one("#mic_test_meter", Static)
        meter.update("Iniciando captura de prueba...")

        def _do_mic_test():
            try:
                cmd = ["arecord", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", "16000", "-q"]
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                start_t = time.time()

                while time.time() - start_t < 3.0:
                    chunk = proc.stdout.read(1024)
                    if not chunk:
                        break
                    count = len(chunk) // 2
                    shorts = struct.unpack(f"{count}h", chunk)
                    sum_sq = sum(s * s for s in shorts)
                    rms = math.sqrt(sum_sq / count) if count > 0 else 0
                    normalized = min(1.0, rms / 32768.0 * 8.0)
                    bars = int(normalized * 30)
                    bar_str = "█" * bars + "░" * (30 - bars)
                    self.call_from_thread(meter.update, f"Nivel: [{bar_str}] {int(normalized * 100)}%")
                    time.sleep(0.06)

                proc.terminate()
                self.call_from_thread(meter.update, "✔ Prueba de micrófono completada.")
            except Exception as e:
                self.call_from_thread(meter.update, f"Error al probar micrófono: {e}")
            finally:
                self.testing_mic = False

        threading.Thread(target=_do_mic_test, daemon=True).start()

    def check_updates_async(self) -> None:
        feedback = self.query_one("#update_feedback", Label)
        feedback.update("Comprobando actualizaciones en GitHub...")

        def _do_check():
            try:
                from core.updater import check_for_updates
                check_for_updates(self.cfg, self.cm, force=True)
                self.call_from_thread(feedback.update, "✔ OpenDictate se encuentra en la última versión disponible.")
            except Exception as e:
                self.call_from_thread(feedback.update, f"Error al verificar: {e}")

        threading.Thread(target=_do_check, daemon=True).start()

    def reset_to_defaults(self) -> None:
        self.cfg = dict(DEFAULT_CONFIG)
        self.notify_user("Valores por defecto cargados. Haz click en Guardar para aplicar.")

    def notify_user(self, msg: str) -> None:
        status_msg = self.query_one("#status_msg", Label)
        status_msg.update(msg)

    def action_save_and_apply(self) -> None:
        """Collect all UI values, persist to SQLite, and force reload on daemon."""
        # STT & Models
        self.cfg["stt_backend"] = self.query_one("#sel_backend", Select).value
        self.cfg["whisper_model_size"] = self.query_one("#sel_active_model", Select).value
        self.cfg["whisper_device"] = self.query_one("#sel_device", Select).value
        self.cfg["whisper_compute_type"] = self.query_one("#sel_compute", Select).value

        try:
            self.cfg["whisper_cpu_threads"] = int(self.query_one("#inp_threads", Input).value)
        except ValueError:
            self.cfg["whisper_cpu_threads"] = 0

        # AI
        self.cfg["ai_enabled"] = self.query_one("#sw_ai", Switch).value
        self.cfg["model"] = self.query_one("#sel_gemini_model", Select).value
        self.cfg["api_key"] = self.query_one("#inp_api_key", Input).value.strip()
        self.cfg["llm_thinking_level"] = self.query_one("#sel_thinking", Select).value
        self.cfg["system_prompt"] = self.query_one("#txt_system_prompt", TextArea).text

        # Audio & VAD
        self.cfg["realtime_mode"] = self.query_one("#sw_realtime", Switch).value
        self.cfg["echo_cancellation_enabled"] = self.query_one("#sw_aec", Switch).value

        try:
            self.cfg["chunk_vad_energy_threshold"] = float(self.query_one("#inp_vad_threshold", Input).value)
        except ValueError:
            pass

        try:
            self.cfg["chunk_silence_duration"] = float(self.query_one("#inp_silence_duration", Input).value)
        except ValueError:
            pass

        try:
            self.cfg["chunk_max_duration"] = float(self.query_one("#inp_max_duration", Input).value)
        except ValueError:
            pass

        # Voice commands
        self.cfg["voice_commands_enabled"] = self.query_one("#sw_voice", Switch).value
        try:
            self.cfg["voice_command_threshold"] = float(self.query_one("#inp_voice_threshold", Input).value)
        except ValueError:
            pass

        try:
            self.cfg["voice_command_silence_pause"] = float(self.query_one("#inp_voice_silence", Input).value)
        except ValueError:
            pass

        # General & Multimedia
        self.cfg["ui_language"] = self.query_one("#sel_language", Select).value
        self.cfg["auto_send"] = self.query_one("#sw_autosend", Switch).value
        self.cfg["restore_window_focus"] = self.query_one("#sw_focus", Switch).value
        self.cfg["pause_media"] = self.query_one("#sw_mpris", Switch).value
        self.cfg["hide_bubble"] = self.query_one("#sw_hide_bubble", Switch).value

        # Omarchy desktop indicator mode
        if os.path.exists(os.path.expanduser("~/.config/omarchy/plugins/com.kirulab.opendictate")):
            self.cfg["indicator_mode"] = "omarchy"
            self.cfg["use_appindicator"] = False

        # Persist
        self.cm.save_config(self.cfg, explicit_api_key_update=True)

        # Notify running daemon via socket
        self._notify_daemon_reload()
        self.exit()

    def _notify_daemon_reload(self) -> None:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(SOCKET_PATH)
            s.sendall(b"reload-config")
            s.close()
        except Exception:
            pass

    def action_quit_app(self) -> None:
        self.exit()


def run_tui() -> None:
    """Launch the settings TUI application."""
    app = SettingsTUI()
    app.run()


if __name__ == "__main__":
    run_tui()

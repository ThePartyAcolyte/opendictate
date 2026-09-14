# Auditoría de Internacionalización (i18n)

## TAREA-44 — Agregar claves i18n para estados Gemini Live y calibración AEC

**Hallazgo:** ID-DAEMON-10, ID-DAEMON-11, ID-I18N-03, ID-I18N-04 | **Severidad:** Media | **Prerrequisito:** Fase 4 completa

### Contexto
Estados específicos de Gemini Live y los mensajes de calibración AEC (Eco) están hardcodeados en español/inglés en lugar de usar el sistema `i18n`.

### Archivos a modificar / crear
- `i18n/en.py` (y `es.py`, `de.py`, `fr.py`)
- `opendictate-daemon.py`
- `core/aec.py`

### Cambio requerido

#### `i18n/en.py` — Antes (línea ~430)
```python
    "toast_gemini_recovered_cloud": "Gemini connection restored. Transcription completed in the cloud.",
}
```
#### `i18n/en.py` — Después
```python
    "toast_gemini_recovered_cloud": "Gemini connection restored. Transcription completed in the cloud.",
    "status_gemini_ready": "Ready (Gemini Live)",
    "status_gemini_recording": "Recording (Gemini Live)...",
    "aec_insufficient_audio": "Insufficient audio captured for calibration.",
    "aec_latency_result": "Latency: {delay_ms} ms (Correlation: {peak_val})",
    "aec_low_correlation": "Low correlation ({peak_val}). Ensure speakers are audible.",
    "aec_calibration_error": "Calibration error: {error}",
}
```
*(Repetir en `es.py`, `de.py`, `fr.py` con sus respectivas traducciones).*

#### `opendictate-daemon.py` — Antes (línea ~296)
```python
        if key == "ready":
            if backend == "gemini_live" and self.config.get("api_key"):
                status_text = "Listo (Gemini Live)"
            else:
                status_text = self.i18n.t("ready", self.engine.model_size)
        elif key == "recording" and backend == "gemini_live":
            status_text = "Grabando (Gemini Live)..."
```
#### `opendictate-daemon.py` — Después
```python
        if key == "ready":
            if backend == "gemini_live" and self.config.get("api_key"):
                status_text = self.i18n.t("status_gemini_ready")
            else:
                status_text = self.i18n.t("ready", self.engine.model_size)
        elif key == "recording" and backend == "gemini_live":
            status_text = self.i18n.t("status_gemini_recording")
```

#### `core/aec.py` — Antes (líneas ~238, 248)
```python
                    message="Audio capturado insuficiente para calibración."
```
```python
            msg = f"Latencia: {delay_ms:.1f} ms (Correlación: {peak_val:.2f})"
            if not is_valid:
                msg = f"Baja correlación ({peak_val:.2f}). Asegúrese de que los altavoces se escuchan."
```
#### `core/aec.py` — Después
```python
                    message=i18n.t("aec_insufficient_audio")
```
```python
            msg = i18n.t("aec_latency_result", delay_ms=f"{delay_ms:.1f}", peak_val=f"{peak_val:.2f}")
            if not is_valid:
                msg = i18n.t("aec_low_correlation", peak_val=f"{peak_val:.2f}")
```

### Verificación
```bash
python3 -c "from i18n.en import STRINGS; print('status_gemini_ready' in STRINGS)"
```

---

## TAREA-45 — Migrar strings hardcodeados adicionales del daemon a i18n

**Hallazgo:** ID-DAEMON-21 | **Severidad:** Baja | **Prerrequisito:** Fase 4 completa

### Contexto
El daemon notifica eventos de sesión reservada o guardado de perfiles usando strings hardcodeados.

### Archivos a modificar / crear
- `i18n/en.py` (y demás idiomas)
- `opendictate-daemon.py`

### Cambio requerido

#### `opendictate-daemon.py` — Antes (líneas 409, 474, 1524)
```python
            self.show_notification("OpenDictate", "Reserva de dictado cancelada")
```
```python
                self.show_notification("OpenDictate", f"Perfil '{app_class}' guardado")
```
```python
        self.update_status(f"Listo (Reservado para {app_name})")
```
#### `opendictate-daemon.py` — Después
```python
            self.show_notification("OpenDictate", self.i18n.t("notif_reservation_cancelled"))
```
```python
                self.show_notification("OpenDictate", self.i18n.t("notif_profile_saved", app_class=app_class))
```
```python
        self.update_status(self.i18n.t("status_reserved", app_name=app_name))
```

### Verificación
Revisión visual de que los strings se traducen correctamente.

---

## TAREA-46 — Migrar strings de `config_ui.py` y `tray.py` a i18n

**Hallazgo:** ID-UI-14, ID-UI-15 | **Severidad:** Baja | **Prerrequisito:** Fase 4 completa

### Contexto
Labels de comandos de voz en UI de configuración y tooltips en la bandeja de sistema no están internacionalizados.

### Archivos a modificar / crear
- `opendictate_config_ui.py`
- `ui/tray.py`

### Cambio requerido

#### `opendictate_config_ui.py` — Antes (líneas 2227, 2245, 2256)
```python
            btn_add_alt = Gtk.Button(label="➕ Añadir Frase")
```
```python
                p_name_lbl = Gtk.Label(label=f"🗣️ \"{phrase.name}\"", xalign=0)
```
```python
                btn_edit = Gtk.Button(label="🎙️ Muestras / Calibrar")
```
#### `opendictate_config_ui.py` — Después
```python
            btn_add_alt = Gtk.Button(label=self.i18n.t("btn_add_phrase"))
```
```python
                p_name_lbl = Gtk.Label(label=f"🗣️ \"{phrase.name}\"", xalign=0) # (No requiere i18n si es valor directo del usuario)
```
```python
                btn_edit = Gtk.Button(label=self.i18n.t("btn_edit_samples"))
```

#### `ui/tray.py` — Antes (línea 251)
```python
                    self.indicator.set_tooltip_text("OpenDictate - Micrófono saturado")
```
#### `ui/tray.py` — Después
```python
                    self.indicator.set_tooltip_text(self.i18n.t("tooltip_mic_saturated"))
```

---

## TAREA-47 — Activar sistema i18n en `ui/settings_tui.py` y `ui/wizard_tui.py`

**Hallazgo:** ID-I18N-01, ID-I18N-02, ID-UI-13 | **Severidad:** Alta | **Prerrequisito:** Fase 4 completa

### Contexto
Las interfaces de terminal TUI instancian el traductor (`self.i18n = get_translator(...)`) pero siguen usando cadenas hardcodeadas (e.g. `TabPane("Modelos y STT")`).

### Archivos a modificar / crear
- `ui/settings_tui.py`
- `ui/wizard_tui.py`

### Cambio requerido (Parcial)

#### `ui/settings_tui.py` — Antes (líneas ~313, 338, 339)
```python
            with TabPane("Modelos y STT", id="tab_models"):
```
```python
                            yield Button("Activar Seleccionado", id="btn_activate_model", variant="primary", classes="btn-action")
                            yield Button("Descargar Modelo", id="btn_download_model", variant="success", classes="btn-action")
```
#### `ui/settings_tui.py` — Después
```python
            with TabPane(self.i18n.t("tab_models"), id="tab_models"):
```
```python
                            yield Button(self.i18n.t("btn_activate"), id="btn_activate_model", variant="primary", classes="btn-action")
                            yield Button(self.i18n.t("btn_download_model"), id="btn_download_model", variant="success", classes="btn-action")
```
*(Nota: Aplicar esto a los botones y pestañas principales en `settings_tui.py` y `wizard_tui.py`)*

---

## TAREA-48 — Centralizar constantes de modelos en `core/config.py`

**Hallazgo:** ID-UI-08 | **Severidad:** Media | **Prerrequisito:** Ninguno

### Contexto
Múltiples archivos definen su propia copia de las listas `WHISPER_MODELS` y `GEMINI_MODELS` (con descripciones diferentes). Deben estar centralizadas.

### Archivos a modificar / crear
- `core/config.py`
- `ui/settings_tui.py`
- `ui/wizard_tui.py`

### Cambio requerido

#### `core/config.py` — Después (al final del archivo)
```python
WHISPER_MODELS_LIST = [
    ("tiny", "39 MB", "Ultraligero / CPU"),
    ("base", "74 MB", "Rápido / CPU o GPU"),
    ("small", "244 MB", "Balance ideal (Recomendado)"),
    ("medium", "769 MB", "Alta precisión / GPU"),
    ("large-v3", "1.5 GB", "Máxima precisión"),
    ("large-v3-turbo", "809 MB", "Rápido y preciso"),
]

GEMINI_MODELS_LIST = [
    ("Gemma 4 26B (Recomendado)", "gemma-4-26b-a4b-it"),
    ("Gemini 2.5 Flash", "gemini-2.5-flash"),
    ("Gemini 2.5 Pro", "gemini-2.5-pro"),
    ("Gemini 2.0 Flash", "gemini-2.0-flash"),
]
```

#### `ui/settings_tui.py` — Antes (líneas ~48)
```python
WHISPER_MODELS = [
    ("tiny", "39 MB", "Ultraligero / CPU"),
    ...
]
GEMINI_MODELS = [
    ("Gemma 4 26B (Recomendado)", "gemma-4-26b-a4b-it"),
    ...
]
```
#### `ui/settings_tui.py` — Después
```python
from core.config import WHISPER_MODELS_LIST as WHISPER_MODELS, GEMINI_MODELS_LIST as GEMINI_MODELS
```
*(Aplicar misma limpieza en `wizard_tui.py` y `opendictate_config_ui.py` donde corresponda).*

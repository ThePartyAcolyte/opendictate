# Plan de Auditoría, Saneamiento y Refactorización de OpenDictate

Este documento consolida los hallazgos de la auditoría integral de código de **OpenDictate** y define la hoja de ruta detallada, paso a paso, para sanear la base de código, corregir defectos latentes, optimizar el rendimiento y eliminar código muerto y duplicado.

---

## 1. Resumen Ejecutivo y Diagnóstico Global

```
+-------------------------------------------------------------------------------+
|                       ESTADO ACTUAL DE LA BASE DE CÓDIGO                      |
+-------------------------------------------------------------------------------+
|  Archivos Python analizados  :  50 archivos en workspace                      |
|  Líneas totales de código    :  ~18,200 líneas                                |
|  Módulos monolíticos clave   :  opendictate_config_ui.py (2,484 líneas)       |
|                                 opendictate-daemon.py    (1,873 líneas)       |
|                                 ui/wizard.py             (1,418 líneas)       |
|  Cobertura de claves i18n    :  397/397 sincronizadas (EN, ES, DE, FR)       |
|  Pruebas Unitarias           :  41 pasadas / 0 fallidas (con entorno venv)    |
|  Defectos Críticos Detectados:  5 hallazgos de alta severidad                 |
+-------------------------------------------------------------------------------+
```

---

## 2. Catálogo Detallado de Hallazgos

### 2.1. Defectos Críticos y Cuellos de Botella de Rendimiento

| ID | Componente / Archivo | Severidad | Descripción del Problema | Impacto en Producción |
| :--- | :--- | :--- | :--- | :--- |
| **`CRIT-01`** | `opendictate-daemon.py`<br>*(Línea 852, 341)* | **Crítica** | En el bucle de audio de 100ms, `on_level_update` invoca `export_state(force=False)`, el cual llama sincrónicamente a `get_open_windows_list()`. Esto ejecuta `subprocess.run(["hyprctl", "clients", "-j"])` o `wmctrl -lx` **10 veces por segundo** durante la grabación. | Picos intensos de CPU, degradación de la captura de audio y micro-congelamientos de la interfaz. |
| **`CRIT-02`** | `core/config.py`<br>*(Línea 121)* | **Crítica** | Falta `import time`. En el método `_get_api_key_safe()`, la línea 121 ejecuta `time.sleep(0.05)` si el acceso a keyring falla. | Si la consulta al keyring arroja una excepción transitoria, el daemon colapsa con `NameError: name 'time' is not defined`. |
| **`CRIT-03`** | `ui/wizard_tui.py`<br>*(Línea 38, Línea 229)* | **Crítica** | Importa `get_system_hardware_info` desde `core.hardware`, función inexistente en dicho módulo. | Ejecutar `opendictate --wizard-tui` falla inmediatamente con `ImportError`. |
| **`CRIT-04`** | `install.sh`<br>*(Líneas 80–85)* | **Alta** | La variable `$OPENDECK_PLUGINS_DIR` no está definida en `install.sh`. | `mkdir -p ""` y `cp -r ... ""` operan sobre una ruta vacía o el directorio raíz de trabajo. |
| **`CRIT-05`** | `core/ipc.py`<br>*(Línea 47)* | **Alta** | Búfer fijo de lectura de socket Unix limitado a 1024 bytes (`conn.recv(1024)`). | Payloads JSON de configuración extensa o perfiles (`save-profile:`, `set-config:`) que superen 1 KB sufren truncamiento y fallan al decodificarse. |

---

### 2.2. Código Muerto y Archivos Obsoletos

#### A. Scripts Temporales y Parches en Raíz
* **`patch_changelog.py` (Líneas 1–20)**: Script de parche desechable que insertaba la entrada del 2026-09-04 en `CHANGELOG.md`. Ya está integrada en el archivo principal.
* **`patch_window_utils.py` (Líneas 1–113)**: Script desechable utilizado para agregar funciones de Herder a `core/window_utils.py`. Las funciones ya forman parte del módulo.
* **`i18n.py` (Líneas 1–18)**: Capa legacy en raíz redundante con `i18n/__init__.py`. Todo el proyecto ya importa desde el paquete `i18n`.

#### B. Métodos y Páginas Huérfanas
* **`ui/wizard.py` (`_build_page_voice_commands`, Líneas 511–636)**: Página descartada durante el rediseño a 7 pasos del asistente inicial. Sus métodos auxiliares de calibración (`_on_wizard_calibrate_aec`, `_on_wizard_calibrate_noise`, `_record_wizard_sample`, `_clear_wizard_sample`) quedaron desconectados.
* **`ui/wizard.py` (Líneas 1395–1396)**: Referencia a un método `_save_autostart()` que no existe en la clase `FirstRunWizard`.
* **`core/vad.py` (`get_trailing_silence_duration`, Líneas 124–130)**: Método auxiliar con cero referencias en todo el código base.

#### C. Importaciones Inutilizadas
* **`core/engine.py`**: `import time`, `from typing import Callable`.
* **`core/llm.py`**: `import os`, `import time`, `import subprocess`.
* **`core/dbus_service.py`**: `import uuid`.
* **`opendictate-daemon.py`**: `from gi.repository import Gdk`.
* **`plugins/com.kirulab.opendictate.sdplugin/plugin.py`**: Duplicación de `import base64` (Líneas 14 y 24) y `import signal` no utilizado.

---

### 2.3. Código Duplicado y Redundancias

```
+-------------------------------------------------------------------------------+
|                            MAPA DE DUPLICACIONES                              |
+-------------------------------------------------------------------------------+
| 1. Acceso a BD SQLite   : opendictate_config_ui.py vs. core/config.py         |
| 2. Detección Ventanas   : opendictate_config_ui.py vs. core/window_utils.py   |
| 3. Plantilla Autostart  : client.py vs. config_ui.py vs. install.sh           |
| 4. Paleta Omarchy TUI   : settings_tui.py vs. wizard_tui.py                   |
| 5. Constantes Modelos   : Tuplas hardcodeadas en settings_tui y wizard_tui    |
+-------------------------------------------------------------------------------+
```

1. **Bypass de `ConfigManager` en `AppProfilesDialog`**:
   [`opendictate_config_ui.py`](file:///home/butcherwutcher/Projects/dev/dictate-whisper/opendictate_config_ui.py#L274) abre conexiones manuales `sqlite3.connect(self.db_path)` en lugar de utilizar `ConfigManager.get_app_profile()`, `save_app_profile()` y `delete_app_profile()`.
2. **Detección Duplicada de Aplicaciones**:
   [`opendictate_config_ui.py`](file:///home/butcherwutcher/Projects/dev/dictate-whisper/opendictate_config_ui.py#L326) implementa `get_open_apps()` con `pyatspi` exclusivamente, ignorando el resolvedor multi-backend [`core.window_utils.get_open_windows_list`](file:///home/butcherwutcher/Projects/dev/dictate-whisper/core/window_utils.py#L355).
3. **Generación Duplicada de Archivo `.desktop`**:
   Lógica replicada en 3 archivos independientes (`opendictate-client.py`, `opendictate_config_ui.py`, `install.sh`).
4. **Paleta de Colores de Omarchy Shell**:
   La función `get_omarchy_palette()` está copiada de forma idéntica en [`ui/settings_tui.py`](file:///home/butcherwutcher/Projects/dev/dictate-whisper/ui/settings_tui.py#L97) y [`ui/wizard_tui.py`](file:///home/butcherwutcher/Projects/dev/dictate-whisper/ui/wizard_tui.py#L64).

---

### 2.4. Código Desactivado, Manejo de Errores y Logging

* **Supresión silenciosa**: Más de 25 bloques `except Exception: pass` sin traza `logging.debug()` en [`ui/tray.py`](file:///home/butcherwutcher/Projects/dev/dictate-whisper/ui/tray.py#L87), [`core/hardware.py`](file:///home/butcherwutcher/Projects/dev/dictate-whisper/core/hardware.py#L27) y [`core/ipc.py`](file:///home/butcherwutcher/Projects/dev/dictate-whisper/core/ipc.py#L78).
* **Llamadas `print()` directas**: Uso de `print()` en lugar de `logging.error()` / `logging.info()` en [`opendictate_config_ui.py`](file:///home/butcherwutcher/Projects/dev/dictate-whisper/opendictate_config_ui.py#L288) y [`launch_wizard.py`](file:///home/butcherwutcher/Projects/dev/dictate-whisper/launch_wizard.py#L27).
* **Textos hardcodeados fuera de i18n**: Cadenas en español hardcodeadas en estados del daemon (`"Listo (Gemini Live)"`, `"Grabando (Gemini Live)..."`) y mensajes de calibración en [`core/aec.py`](file:///home/butcherwutcher/Projects/dev/dictate-whisper/core/aec.py#L238).

---

## 3. Plan de Acción y Tareas de Refactorización

```
=================================================================================
 FASES DE EJECUCIÓN DEL PLAN DE SANEAMIENTO
=================================================================================
 [FASE 1] -> Corrección de Defectos Críticos y Rendimiento
 [FASE 2] -> Eliminación de Archivos Obsoletos y Código Muerto
 [FASE 3] -> Desduplicación, Unificación y Abstracción de ConfigManager
 [FASE 4] -> Estandarización de Logging, Errores e Internacionalización
 [FASE 5] -> Verificación Integral, Pruebas Unitarias y Despliegue
=================================================================================
```

### Fase 1: Corrección de Defectos Críticos y Rendimiento

1. **Optimizar el bucle de nivel de audio en `opendictate-daemon.py`**:
   - Desacoplar la llamada a `get_open_windows_list()` de `export_state(force=False)` en la actualización de nivel de audio (100ms).
   - Cachear la lista de ventanas abiertas o actualizarla únicamente ante eventos de cambio de foco o en un temporizador de baja frecuencia (ej. cada 3 segundos).
2. **Reparar importación en `core/config.py`**:
   - Agregar `import time` en los imports principales de `core/config.py`.
3. **Reparar detección de hardware en `ui/wizard_tui.py`**:
   - Reemplazar la importación de `get_system_hardware_info` por el uso combinado de `get_gpu_info()` y `get_system_ram_gb()`.
4. **Corregir ruta de plugins OpenDeck en `install.sh`**:
   - Definir `OPENDECK_PLUGINS_DIR="$HOME/.config/opendeck/plugins"` en las variables iniciales de `install.sh`.
5. **Robustecer recepción en `core/ipc.py`**:
   - Implementar lectura de stream continuo hasta cierre de conexión (`while True: chunk = conn.recv(4096)...`) para soportar payloads JSON de cualquier tamaño.

---

### Fase 2: Eliminación de Archivos Obsoletos y Código Muerto

1. **Eliminar scripts residuales en raíz**:
   - Eliminar `patch_changelog.py` y `patch_window_utils.py`.
   - Eliminar `i18n.py` en la raíz (actualizando `install.sh`, `packaging/build_arch.sh` y `packaging/build_deb.sh` para no requerirlo).
2. **Limpiar imports y métodos huérfanos**:
   - Eliminar importaciones no utilizadas en `core/engine.py`, `core/llm.py`, `core/dbus_service.py`, `opendictate-daemon.py` y `plugins/.../plugin.py`.
   - Eliminar método muerto `_build_page_voice_commands` y sus funciones auxiliares en `ui/wizard.py`.
   - Eliminar referencia a `_save_autostart()` en `ui/wizard.py`.
   - Eliminar `get_trailing_silence_duration` en `core/vad.py` o integrarlo en la evaluación de corte.

---

### Fase 3: Desduplicación, Unificación y Abstracción

1. **Encapsulación de Base de Datos en `opendictate_config_ui.py`**:
   - Refactorizar `AppProfilesDialog` para utilizar directamente `self.config_manager.get_app_profile()`, `set_app_profile()`, `delete_app_profile()` y `get_all_app_profiles()`.
   - Reemplazar `AppProfilesDialog.get_open_apps` por `core.window_utils.get_open_windows_list()`.
2. **Unificación de Utilidades TUI**:
   - Centralizar la función `get_omarchy_palette()` en `ui/__init__.py` o `core/hardware.py` y consumirla de forma compartida desde `ui/settings_tui.py` y `ui/wizard_tui.py`.
   - Centralizar las tuplas de modelos y configuraciones en `core/config.py`.
3. **Helper Común para `.desktop` de Autostart**:
   - Centralizar la creación y actualización del archivo `.desktop` en un método helper dentro de `core/config.py` (`ConfigManager.set_autostart_enabled(enabled: bool)`).

---

### Fase 4: Estandarización de Logging, Errores e Internacionalización

1. **Reemplazo de `print()` por `logging`**:
   - Sustituir `print()` residuales en `opendictate_config_ui.py`, `opendictate-daemon.py` y `launch_wizard.py` por `logging.error()`, `logging.warning()` o `logging.info()`.
2. **Reemplazo de `except Exception: pass`**:
   - Agregar `logging.debug(f"...: {e}")` en todos los bloques de captura de errores silenciosos en `ui/tray.py`, `core/hardware.py` y `core/ipc.py`.
3. **Migración de Cadenas Faltantes a `i18n`**:
   - Agregar claves i18n para los estados de Gemini Live en `opendictate-daemon.py` y para los diagnósticos de calibración en `core/aec.py`.

---

### Fase 5: Verificación, Pruebas y Despliegue

1. **Ejecución de Pruebas Unitarias**:
   - Ejecutar la suite completa: `~/.local/share/opendictate/.venv/bin/python -m unittest discover -s tests`.
   - Verificar que todos los tests pasen al 100% sin advertencias de recursos (`ResourceWarning`).
2. **Despliegue Local Automático**:
   - Ejecutar `./install.sh` para desplegar en `~/.local/share/opendictate/`.
   - Verificar la inicialización limpia del daemon y la apertura sin errores de `opendictate --settings`, `opendictate --wizard` y `opendictate --settings-tui`.

---

## 4. Matriz de Validación Post-Saneamiento

| Prueba de Validación | Comando / Procedimiento | Resultado Esperado |
| :--- | :--- | :--- |
| **Pruebas de Unidad** | `~/.local/share/opendictate/.venv/bin/python -m unittest discover -s tests` | 41/41 tests OK, 0 errores. |
| **Inicio del Daemon** | `opendictate --start` | Daemon inicia en `/tmp/opendictate.socket` sin saturar CPU durante grabación. |
| **Grabación y Consumo de CPU** | `opendictate --toggle-record-send` | Consumo mínimo de CPU en grabación (sin llamadas masivas a `hyprctl`). |
| **Panel de Ajustes GTK** | `opendictate --settings` | Apertura fluida, guardado de perfiles SQLite a través de `ConfigManager`. |
| **Asistente TUI** | `opendictate --wizard-tui` | Apertura correcta sin errores de importación de hardware. |
| **Plugins OpenDeck y GNOME** | Inspección de `~/.config/opendeck/plugins` | Plugins desplegados en la ruta correcta. |

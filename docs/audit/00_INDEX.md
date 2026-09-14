# OpenDictate — Plan de Saneamiento: Índice Maestro

## Instrucciones para el Agente Ejecutor
1. **Ejecución Secuencial**: Lee las fases en orden. Las fases 1 y 2 son **BLOQUEANTES**; si falla una verificación en estas fases, detente inmediatamente y reporta el problema.
2. **Revisión de Tareas**: Cada archivo de fase contiene un conjunto de tareas con el contexto necesario, el archivo a modificar y el bloque de código exacto (diff) que debe aplicarse.
3. **Verificación**: Después de aplicar el cambio de una tarea, ejecuta el comando de verificación proporcionado para confirmar que la aplicación fue exitosa antes de continuar con la siguiente.
4. **Instalación Post-Iteración**: Recuerda ejecutar `./install.sh` después de cada bloque de cambios importantes para desplegar localmente en `~/.local/share/opendictate/`.

## Orden de Ejecución

| Fase | Archivo | Tareas | Prerrequisito | Estado |
|---|---|---|---|---|
| **Fase 1** | `01_crashes_criticos.md` | 6 (TAREA-01 a TAREA-06) | Ninguno | COMPLETADA |
| **Fase 2** | `02_rendimiento_seguridad.md` | 5 (TAREA-07 a TAREA-11) | Fase 1 completada | COMPLETADA |
| **Fase 3** | `03_empaquetado_instalacion.md` | 9 (TAREA-12 a TAREA-20) | Fase 2 completada | COMPLETADA |
| **Fase 4** | `04_codigo_muerto.md` | 15 (TAREA-21 a TAREA-35) | Fase 3 completada | COMPLETADA |
| **Fase 5** | `05_deduplicacion_ui.md` | 4 (TAREA-36 a TAREA-39) | Fase 4 completada | COMPLETADA |
| **Fase 6** | `06_logging_errores.md` | 4 (TAREA-40 a TAREA-43) | Fase 5 completada | COMPLETADA |
| **Fase 7** | `07_i18n_strings.md` | 5 (TAREA-44 a TAREA-48) | Fase 6 completada | COMPLETADA |
| **Fase 8** | `08_tests_documentacion.md` | 8 (TAREA-49 a TAREA-56) | Fase 7 completada | COMPLETADA |

## Checklist Global de Progreso

### Fase 1: Crashes Críticos
- [x] TAREA-01: Agregar `import time` en `core/config.py`
- [x] TAREA-02: Corregir ImportError en `ui/wizard_tui.py`
- [x] TAREA-03: Corregir nombre de atributo IPC en `quit_app()`
- [x] TAREA-04: Corregir navegación del GTK Wizard (step vacío)
- [x] TAREA-05: Implementar `_save_autostart()` en `FirstRunWizard`
- [x] TAREA-06: Eliminar definición duplicada de `_notify_daemon_reload`

### Fase 2: Rendimiento y Seguridad
- [x] TAREA-07: Optimizar bucle de audio — cachear llamadas costosas en `export_state()`
- [x] TAREA-08: Robustecer lectura IPC — reemplazar `recv(1024)` por bucle hasta EOF
- [x] TAREA-09: Mover socket IPC a `$XDG_RUNTIME_DIR`
- [x] TAREA-10: Eliminar archivo de captura de pantalla tras upload en `core/llm.py`
- [x] TAREA-11: Corregir precedencia de operadores en detección GPU NVIDIA (`core/hardware.py`)

### Fase 3: Empaquetado e Instalación
- [x] TAREA-12: Definir `$OPENDECK_PLUGINS_DIR` en `install.sh`
- [x] TAREA-13: Agregar `chmod +x` para `opendictate_config_ui.py` en `install.sh`
- [x] TAREA-14: `install.sh` debe usar `-r requirements.txt`
- [x] TAREA-15: Agregar `websockets` y `Pillow` a `requirements.txt`
- [x] TAREA-16: `build_deb.sh` postinst — incluir dependencias adicionales
- [x] TAREA-17: `build_arch.sh` post_install — crear venv e instalar dependencias
- [x] TAREA-18: `uninstall.sh` — limpiar plugin Omarchy Shell y `shell.json`
- [x] TAREA-19: `plugins/start.sh` — usar Python del venv
- [x] TAREA-20: `install.sh` — agregar `~/.local/bin` al PATH tras instalar `uv`

### Fase 4: Código Muerto
- [x] TAREA-21: Eliminar `patch_changelog.py`
- [x] TAREA-22: Eliminar `patch_window_utils.py`
- [x] TAREA-23: Eliminar `i18n.py` (raíz) y actualizar referencias
- [x] TAREA-24: Eliminar métodos de comandos de voz en `ui/wizard.py`
- [x] TAREA-25: Eliminar `get_trailing_silence_duration` en `core/vad.py`
- [x] TAREA-26: Eliminar stub duplicado de `_streaming_transcriber_loop` en `opendictate-daemon.py`
- [x] TAREA-27: Documentar `parse_verbal_punctuation` como TD-002 en `TECHNICAL_DEBT.md`
- [x] TAREA-28: Limpieza de imports en `core/engine.py`
- [x] TAREA-29: Limpieza de imports en `core/llm.py`
- [x] TAREA-30: Limpieza de imports en `core/dbus_service.py`
- [x] TAREA-31: Limpieza de imports en `opendictate-daemon.py`
- [x] TAREA-32: Limpieza de imports en `core/aec.py`
- [x] TAREA-33: Limpieza de imports en `plugin.py`
- [x] TAREA-34: Mover imports inline al nivel de módulo en `core/window_utils.py`
- [x] TAREA-35: Eliminar claves i18n huérfanas

### Fase 5: Deduplicación UI
- [x] TAREA-36: Refactorizar `AppProfilesDialog` para usar API de `ConfigManager`
- [x] TAREA-37: Reemplazar `get_open_apps()` por `get_open_windows_list()`
- [x] TAREA-38: Centralizar `get_omarchy_palette()` en `core/hardware.py`
- [x] TAREA-39: Centralizar generación de autostart `.desktop` en `ConfigManager`

### Fase 6: Logging y Errores
- [x] TAREA-40: Reemplazar prints por logging en launch_wizard.py y opendictate_config_ui.py
- [x] TAREA-41: Reemplazar except silenciosos por logging.debug en core/hardware.py y core/ipc.py
- [x] TAREA-42: Auditar y estructurar logging de excepciones en opendictate-daemon.py
- [x] TAREA-43: Auditar excepts en componentes UI y configurar RotatingFileHandler en plugin.py

### Fase 7: I18n y Strings
- [x] TAREA-44: Agregar claves i18n para estados Gemini Live y calibración AEC
- [x] TAREA-45: Migrar strings hardcodeados del daemon a i18n
- [x] TAREA-46: Migrar strings de config_ui.py y tray.py a i18n
- [x] TAREA-47: Conectar i18n en interfaces TUI
- [x] TAREA-48: Centralizar constantes de modelos en core/config.py

### Fase 8: Tests y Documentación
- [x] TAREA-49: Refactorizar test_dbus_integration.py para usar unittest.TestCase y MagicMock
- [x] TAREA-50: Test de regresión para Keyring en test_core_config.py
- [x] TAREA-51: Robustecer tests y buffers de recepción IPC
- [x] TAREA-52: Crear test_wizard_tui.py
- [x] TAREA-53: Corregir ejemplo nc en IPC_PROTOCOL_SPECIFICATION.md
- [x] TAREA-54: Actualizar catálogo de comandos IPC en Especificación
- [x] TAREA-55: Actualizar CHANGELOG.md y TECHNICAL_DEBT.md
- [x] TAREA-56: Corregir TextEncoder en GLib.Bytes para la extensión de GNOME Shell

## Comandos de Verificación Global
Ejecutar estos comandos en la raíz del proyecto para asegurar que las dependencias y la estructura básica sea correcta después de completar el saneamiento.

```bash
# Validar sintaxis en todos los archivos python
python3 -m compileall -q .

# Correr pruebas unitarias (si están configuradas)
python3 -m pytest tests/

# Probar la carga de módulos clave de la UI sin iniciar Gtk
python3 -c "import ui.wizard; import opendictate_config_ui; print('Validación UI OK')"

# Validar el daemon
python3 opendictate-daemon.py --help
```

## Resumen de Hallazgos por Severidad
Este saneamiento resuelve un total de 82 hallazgos distribuidos en las siguientes categorías de severidad:

| Severidad | Cantidad de Hallazgos | Descripción |
|---|---|---|
| **CRÍTICO** | 12 | Errores que causan caídas (crashes) inmediatas o previenen el inicio de la app. |
| **ALTA** | 20 | Fugas de memoria, vulnerabilidades, o errores que afectan el uso normal pero no caen la app inmediatamente. |
| **MEDIA** | 30 | Errores de UI, funciones duplicadas, código muerto, problemas menores de estado y estado de configuración. |
| **BAJA** | 20 | Problemas de consistencia en el código, malas prácticas, strings hardcodeados, o falta de documentación. |
| **TOTAL** | **82** | |

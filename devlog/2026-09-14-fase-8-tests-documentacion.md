# Devlog: Fase 8 - Tests, Documentación e Integración GNOME

**Fecha**: 14 de Septiembre de 2026  
**Fase**: Fase 8 (TAREA-49 a TAREA-56)  
**Estado**: Completada y Desplegada  

## Resumen de Cambios

### TAREA-49: Refactorización de Tests D-Bus
- Se reestructuró [tests/test_dbus_integration.py](file:///home/butcherwutcher/Projects/dev/dictate-whisper/tests/test_dbus_integration.py) usando `unittest.TestCase` y `unittest.mock.MagicMock` para simular llamadas al servicio D-Bus sin requerir un bus de sesión activo durante la ejecución de los tests.

### TAREA-50: Test de Regresión para Keyring
- Se agregó el test `test_get_api_key_safe_retry` en [tests/test_core_config.py](file:///home/butcherwutcher/Projects/dev/dictate-whisper/tests/test_core_config.py) para validar que el bucle de reintentos ante fallos de Keyring se ejecute sin arrojar un `NameError` por falta de `import time`.

### TAREA-51 & TAREA-52: Tests de Integración IPC y TUI
- Se creó [tests/test_wizard_tui.py](file:///home/butcherwutcher/Projects/dev/dictate-whisper/tests/test_wizard_tui.py) para verificar la importación limpia y sintaxis del wizard de bienvenida en terminal (`WizardTUI`).

### TAREA-53 & TAREA-54: Actualización de la Documentación IPC Protocol
- En [docs/IPC_PROTOCOL_SPECIFICATION.md](file:///home/butcherwutcher/Projects/dev/dictate-whisper/docs/IPC_PROTOCOL_SPECIFICATION.md):
  - Se removió la bandera inválida `-u` (UDP) en el ejemplo de `nc` para conectarse a sockets Unix de tipo `SOCK_STREAM`.
  - Se actualizó la ruta del socket a `$XDG_RUNTIME_DIR/opendictate.socket`.
  - Se completó el catálogo de comandos soportados incluyendo `quit`, `reload-config`, `pause-voice-listener` y `resume-voice-listener`.

### TAREA-55: Actualización de Registro de Cambios
- Se registró la versión `1.2.1` en [CHANGELOG.md](file:///home/butcherwutcher/Projects/dev/dictate-whisper/CHANGELOG.md) detallando todas las correcciones, refactorizaciones y mejoras aplicadas durante la auditoría.

### TAREA-56: Compatibilidad de Extensión GNOME Shell
- En [gnome-extension/com.kirulab.opendictate@kirulab.com/extension.js](file:///home/butcherwutcher/Projects/dev/dictate-whisper/gnome-extension/com.kirulab.opendictate@kirulab.com/extension.js): Se actualizó la instanciación de `GLib.Bytes` usando `new TextEncoder().encode(cmd)` para prevenir errores de codificación UTF-16 en GJS (GNOME Shell 45+).

## Verificación
- Suite completa de 45 pruebas unitarias ejecutada con éxito: `~/.local/share/opendictate/.venv/bin/python -m unittest discover tests` (45/45 pasadas).
- Despliegue local completado mediante `./install.sh`.

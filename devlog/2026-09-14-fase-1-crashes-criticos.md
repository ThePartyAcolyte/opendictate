# DevLog: Fase 1 — Crashes Críticos y Errores Fatales

**Fecha:** 2026-09-14
**Estado:** Completado
**Fase de Auditoría:** Fase 1 (TAREA-01 a TAREA-06)

## Resumen de Cambios

En esta primera fase bloqueante del Plan de Saneamiento, se resolvieron 6 problemas críticos que causaban caídas inmediatas del sistema, fallos de importación o comportamientos erróneos en la interfaz de usuario y el daemon.

### Tareas Ejecutadas

1. **TAREA-01: Inyección de `import time` en `core/config.py`**
   - **Archivo:** `core/config.py`
   - **Descripción:** Se añadió la importación del módulo `time` en las cabeceras del archivo para evitar el error `NameError` que ocurría al reintentar la lectura del keyring en `_get_api_key_safe()`.
   - **Verificación:** `from core.config import ConfigManager` ejecutado sin errores.

2. **TAREA-02: Corrección de `ImportError` y claves GPU en `ui/wizard_tui.py`**
   - **Archivo:** `ui/wizard_tui.py`
   - **Descripción:** Se actualizó la importación de `get_system_hardware_info` a `get_gpu_info` desde `core.hardware` y se corrigió la referencia del diccionario de `has_cuda` a `cuda_ready`.
   - **Verificación:** Importación exitosa de `ui.wizard_tui`.

3. **TAREA-03: Corrección de atributo IPC en `quit_app()`**
   - **Archivo:** `opendictate-daemon.py`
   - **Descripción:** Se corrigió el nombre del atributo accedido al cerrar la aplicación (`self.ipc_server` -> `self.ipc`), permitiendo detener el servidor de sockets IPC de forma limpia.
   - **Verificación:** Inspección visual y compilación sintáctica limpia.

4. **TAREA-04: Corrección de índices de navegación en GTK Wizard**
   - **Archivo:** `ui/wizard.py`
   - **Descripción:** Se reordenaron los identificadores de páginas agregadas a `GtkStack` (`step_4` -> `step_3`, `step_5` -> `step_4`, `step_6` -> `step_5`, `step_7` -> `step_6`) eliminando el "hueco" en la navegación por la remoción previa del paso de comandos de voz.
   - **Verificación:** `FirstRunWizard` importado y validado en entorno Gtk.

5. **TAREA-05: Implementación del método `_save_autostart()` en `FirstRunWizard`**
   - **Archivo:** `ui/wizard.py`
   - **Descripción:** Se implementó el método `_save_autostart()` faltante en la clase `FirstRunWizard`, creando/eliminando adecuadamente el archivo `~/.config/autostart/opendictate.desktop` según el estado del switch.
   - **Verificación:** `FirstRunWizard` se inicializa correctamente y dispone del método.

6. **TAREA-06: Eliminación de definición duplicada de `_notify_daemon_reload`**
   - **Archivo:** `opendictate_config_ui.py`
   - **Descripción:** Se eliminó la segunda declaración incompleta de `_notify_daemon_reload` al final de la clase en `opendictate_config_ui.py`, preservando únicamente la definición completa de la línea 1724.
   - **Verificación:** `grep -n 'def _notify_daemon_reload' opendictate_config_ui.py` confirmó exactamente 1 definición.

---

## Verificación Global de Sintaxis de Fase 1

Se ejecutó la compilación de sintaxis sobre todos los archivos del repositorio:
```bash
python3 -m compileall -q .
```
Todos los módulos de la Fase 1 compilaron limpiamente sin errores.

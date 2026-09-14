# DevLog: Fase 5 — Deduplicación y Refactorización UI

**Fecha:** 2026-09-14
**Estado:** Completado
**Fase de Auditoría:** Fase 5 (TAREA-36 a TAREA-39)

## Resumen de Cambios

En esta fase se unificó la lógica repetida entre la interfaz gráfica GTK, las interfaces de consola TUI y los servicios base de configuración, garantizando la observancia de las reglas de nomenclatura simples y orientadas a función.

### Tareas Ejecutadas

1. **TAREA-36: Refactorización de `AppProfilesDialog` con la API de `ConfigManager`**
   - **Archivo:** `opendictate_config_ui.py`
   - **Descripción:** Se eliminaron las consultas e inserciones SQLite directas (`sqlite3.connect`) en el diálogo de perfiles por aplicación, reemplazándolas por invocaciones centralizadas a `ConfigManager` (`get_all_app_profiles`, `get_app_profile`, `save_app_profile`, `delete_app_profile`).

2. **TAREA-37: Sustitución de `get_open_apps()` por `get_open_windows_list()`**
   - **Archivo:** `opendictate_config_ui.py`
   - **Descripción:** Se removió el método redundante `get_open_apps()` en favor de `get_open_windows_list()` proveniente de `core.window_utils`, consolidando la recolección de ventanas activas en el entorno.

3. **TAREA-38: Centralización de `get_omarchy_palette()`**
   - **Archivos:** `core/hardware.py`, `ui/settings_tui.py`, `ui/wizard_tui.py`
   - **Descripción:** Se centralizó la extracción de la paleta semántica de colores de Omarchy en `core/hardware.py`, eliminando las copias idénticas en los módulos TUI e importándolas directamente.

4. **TAREA-39: Centralización del Autostart `.desktop` en `ConfigManager`**
   - **Archivos:** `core/config.py`, `opendictate-client.py`, `opendictate_config_ui.py`, `ui/wizard.py`
   - **Descripción:** Se agregó el método `set_autostart_enabled(enabled: bool)` a `ConfigManager`, abstrayendo la generación y eliminación del archivo `~/.config/autostart/opendictate.desktop` de forma compartida para el cliente CLI, la interfaz GTK y el asistente inicial.

---

## Verificación de Compilación

Se ejecutó la prueba sintáctica global:
```bash
python3 -m compileall -q .
```
Resultado: Todos los módulos compilaron exitosamente.

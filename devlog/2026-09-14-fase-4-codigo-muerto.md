# DevLog: Fase 4 — Código Muerto y Limpieza

**Fecha:** 2026-09-14
**Estado:** Completado
**Fase de Auditoría:** Fase 4 (TAREA-21 a TAREA-35)

## Resumen de Cambios

En esta fase se llevó a cabo una depuración exhaustiva de parches legacy, puentes redundantes, vistas de wizard en desuso e importaciones no utilizadas, manteniendo protegidos todos los motores y lógica de negocio de comandos de voz para el roadmap futuro.

### Tareas Ejecutadas

1. **TAREA-21 & 22: Eliminación de Parches Temporales**
   - **Archivos:** `patch_changelog.py`, `patch_window_utils.py`
   - **Descripción:** Se eliminaron los scripts de parches temporales utilizados en iteraciones pasadas.

2. **TAREA-23: Remoción de `i18n.py` Redundante en Raíz**
   - **Archivos:** `i18n.py`, `install.sh`, `packaging/build_arch.sh`, `packaging/build_deb.sh`, `core/updater.py`
   - **Descripción:** Se eliminó la capa puente `i18n.py` de la raíz del proyecto y se actualizaron todas las referencias en instaladores y scripts de empaquetado para basarse únicamente en el módulo `i18n`.

3. **TAREA-24: Limpieza de Métodos UI en Asistente (`ui/wizard.py`)**
   - **Archivo:** `ui/wizard.py`
   - **Descripción:** Se retiraron las pantallas y callbacks en desuso del Wizard inicial (`_build_page_voice_commands`, `_record_wizard_sample`, `_clear_wizard_sample`, `_on_wizard_calibrate_aec`, `_on_wizard_calibrate_noise`).

4. **TAREA-25: Remoción de `get_trailing_silence_duration`**
   - **Archivo:** `core/vad.py`
   - **Descripción:** Se eliminó la función extinta `get_trailing_silence_duration`.

5. **TAREA-26: Eliminación de Stub Duplicado de `_streaming_transcriber_loop`**
   - **Archivo:** `opendictate-daemon.py`
   - **Descripción:** Se removió la firma vacía duplicada de 4 líneas en `_streaming_transcriber_loop` que sobreescribía al método principal.

6. **TAREA-27: Documentación de Puntuación Verbal y Comandos de Voz en Deuda Técnica**
   - **Archivo:** `TECHNICAL_DEBT.md`
   - **Descripción:** Se registraron `TD-002` (`parse_verbal_punctuation`) y `TD-003` (Integración UI de Comandos de Voz y Calibración AEC) para asegurar su preservación y desarrollo continuo dentro del roadmap.

7. **TAREA-28 a 34: Depuración de Importaciones**
   - **Archivos:** `core/engine.py`, `core/llm.py`, `core/dbus_service.py`, `opendictate-daemon.py`, `core/aec.py`, `plugins/com.kirulab.opendictate.sdplugin/plugin.py`, `core/window_utils.py`
   - **Descripción:** Se eliminaron módulos no utilizados (`time`, `subprocess`, `uuid`, `signal`, `Gdk`, `math`, `Callable`) y se movieron importaciones de bloque a nivel de módulo en `core/window_utils.py`.

8. **TAREA-35: Verificación de Claves i18n**
   - **Archivos:** `i18n/*.py`
   - **Descripción:** Confirmada la limpieza de claves huérfanas en catálogos de idioma.

---

## Verificación de Compilación

Se ejecutó la compilación sintáctica global:
```bash
python3 -m compileall -q .
```
Resultado: Todos los módulos compilaron limpiamente sin errores.

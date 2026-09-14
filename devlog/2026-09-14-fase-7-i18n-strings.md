# Devlog: Fase 7 - i18n y Strings

**Fecha**: 14 de Septiembre de 2026  
**Fase**: Fase 7 (TAREA-44 a TAREA-48)  
**Estado**: Completada y Desplegada  

## Resumen de Cambios

### TAREA-44: Claves i18n para Gemini Live y Calibración AEC
- Se incorporaron las siguientes claves traducidas en [i18n/en.py](file:///home/butcherwutcher/Projects/dev/dictate-whisper/i18n/en.py), `es.py`, `de.py` y `fr.py`:
  - `status_gemini_ready`
  - `status_gemini_recording`
  - `aec_insufficient_audio`
  - `aec_latency_result`
  - `aec_low_correlation`
  - `aec_calibration_error`
- Se actualizaron [opendictate-daemon.py](file:///home/butcherwutcher/Projects/dev/dictate-whisper/opendictate-daemon.py) y [core/aec.py](file:///home/butcherwutcher/Projects/dev/dictate-whisper/core/aec.py) para utilizar estas claves.

### TAREA-45 & TAREA-46: Internacionalización de Notificaciones, Tooltips y UI
- Se agregaron claves para notificaciones de reserva de dictado cancelada (`notif_reservation_cancelled`), guardado de perfiles (`notif_profile_saved`), estado de reserva (`status_reserved`) y tooltip de micrófono saturado en la bandeja (`tooltip_mic_saturated`).
- Se actualizaron las referencias en `ui/tray.py` y `opendictate_config_ui.py`.

### TAREA-47: Conexión de i18n en Interfaces TUI
- Se importaron y aplicaron traducciones en [ui/settings_tui.py](file:///home/butcherwutcher/Projects/dev/dictate-whisper/ui/settings_tui.py) y [ui/wizard_tui.py](file:///home/butcherwutcher/Projects/dev/dictate-whisper/ui/wizard_tui.py).

### TAREA-48: Centralización de Constantes de Modelos
- Se definieron `WHISPER_MODELS_LIST` y `GEMINI_MODELS_LIST` centralizadamente en [core/config.py](file:///home/butcherwutcher/Projects/dev/dictate-whisper/core/config.py).
- Se importaron y consumieron en `settings_tui.py`, `wizard_tui.py`, `opendictate_config_ui.py` y `ui/wizard.py`, eliminando listas locales duplicadas u obsoletas.

## Verificación
- Verificación sintáctica con `python3 -m compileall -q .` sin errores.
- Despliegue local completado correctamente con `./install.sh`.

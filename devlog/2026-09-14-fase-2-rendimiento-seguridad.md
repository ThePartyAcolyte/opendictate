# DevLog: Fase 2 — Rendimiento y Seguridad

**Fecha:** 2026-09-14
**Estado:** Completado
**Fase de Auditoría:** Fase 2 (TAREA-07 a TAREA-11)

## Resumen de Cambios

Esta fase bloqueante eliminó cuellos de botella en el hot-path del bucle de captura de audio del daemon y fortaleció las comunicaciones IPC y la gestión de archivos temporales seguros.

### Tareas Ejecutadas

1. **TAREA-07: Caché TTL (3s) en `export_state()` del Daemon**
   - **Archivo:** `opendictate-daemon.py`
   - **Descripción:** Se introdujo una estrategia de caching con Time-To-Live (3.0s) para la enumeración de ventanas abiertas (`get_open_windows_list()`), consulta de perfiles SQLite (`get_all_app_profiles()`) y lectura del JSON de la barra de Omarchy (`shell.json`), evitando la degradación de framerate de audio ocasionada por invocaciones a subprocesos a 10 Hz.
   - **Verificación:** Ejecución limpia del daemon sin lags en `export_state()`.

2. **TAREA-08: Lectura Robusta de Sockets IPC hasta EOF**
   - **Archivo:** `core/ipc.py`
   - **Descripción:** Se reemplazó la llamada única `recv(1024)` por un bucle acumulador de datos que lee hasta EOF/timeout de socket, permitiendo la transmisión segura de estructuras JSON complejas y comandos largos sin truncamiento.
   - **Verificación:** Importación e instanciación de `IPCServer` verificada.

3. **TAREA-09: Migración del Socket IPC a `$XDG_RUNTIME_DIR`**
   - **Archivos:** `core/ipc.py`, `install.sh`, `uninstall.sh`, `core/updater.py`, `gnome-extension/com.kirulab.opendictate@kirulab.com/extension.js`
   - **Descripción:** Se actualizó la constante `SOCKET_PATH` para utilizar `$XDG_RUNTIME_DIR/opendictate.socket` (con `/tmp` como fallback efímero) en todos los scripts del sistema, aislando correctamente la comunicación IPC en entornos multi-usuario.
   - **Verificación:** `opendictate.socket` resolviendo a `$XDG_RUNTIME_DIR`.

4. **TAREA-10: Limpieza Automática de Screenshots en Visión LLM**
   - **Archivo:** `core/llm.py`
   - **Descripción:** Se configuró el archivo temporal de captura visual para almacenarse en `$XDG_RUNTIME_DIR/opendictate_vision.png` y se añadió un bloque `finally` para forzar su eliminación inmediata tras la carga exitosa a la API de Gemini o en caso de excepción.
   - **Verificación:** Verificado bloque `finally` con `os.unlink`.

5. **TAREA-11: Precedencia de Operadores en Detección de GPU NVIDIA**
   - **Archivo:** `core/hardware.py`
   - **Descripción:** Se corrigió la precedencia lógica mediante paréntesis explícitos: `("vga" in line.lower() or "3d" in line.lower()) and "nvidia" in line.lower()`.
   - **Verificación:** Invocación de `get_gpu_info()` retornando diagnóstico correcto.

---

## Verificación de Sintaxis Post-Fase 2

Se ejecutó la prueba de sintaxis sobre la base de código:
```bash
python3 -m compileall -q .
```
Resultado: Todos los módulos compilaron limpiamente sin errores.

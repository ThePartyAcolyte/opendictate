## TAREA-07 — Optimizar el bucle de audio — cachear llamadas costosas en `export_state()`

**Hallazgo:** CRIT-01 + ID-DAEMON-17 | **Severidad:** Alta | **Prerrequisito:** Ninguno

### Contexto
La función `export_state(force=False)` es llamada 10 veces por segundo desde el callback `on_level_update` en el bucle de audio. En esta función se ejecutan operaciones muy costosas sin caché: obtención de ventanas abiertas por subprocess, consultas SQLite a la base de datos de perfiles y lecturas sincrónicas de `shell.json`. Estas llamadas en el hot path pueden inducir bloqueos y pérdida de cuadros de audio. Es imperativo implementar una caché con un TTL (Time-To-Live) de 3 segundos para mitigarlo.

### Archivos a modificar
- `opendictate-daemon.py`

### Cambio requerido

#### `opendictate-daemon.py` — Antes (línea 104)
```python
        self.processing_start_time: float = 0.0
        self._last_state_export_time: float = 0.0
        self.timer_id: Optional[int] = None
```

#### `opendictate-daemon.py` — Después
```python
        self.processing_start_time: float = 0.0
        self._last_state_export_time: float = 0.0
        self._cache_windows = []
        self._cache_windows_ts = 0.0
        self._cache_profiles = []
        self._cache_profiles_ts = 0.0
        self._cache_shell = None
        self._cache_shell_ts = 0.0
        self.timer_id: Optional[int] = None
```

#### `opendictate-daemon.py` — Antes (línea 305)
```python
        bar_pos = "right"
        try:
            shell_p = os.path.expanduser("~/.config/omarchy/shell.json")
            if os.path.exists(shell_p):
                with open(shell_p, "r") as f:
                    s_data = json.load(f)
                b_layout = s_data.get("bar", {}).get("layout", {})
                for section in ["left", "center", "right"]:
                    if any(isinstance(it, dict) and it.get("id") == "com.kirulab.opendictate" for it in b_layout.get(section, [])):
                        bar_pos = section
                        break
        except Exception:
            pass
```

#### `opendictate-daemon.py` — Después
```python
        bar_pos = "right"
        if now - self._cache_shell_ts > 3.0:
            try:
                shell_p = os.path.expanduser("~/.config/omarchy/shell.json")
                if os.path.exists(shell_p):
                    with open(shell_p, "r") as f:
                        self._cache_shell = json.load(f)
            except Exception:
                self._cache_shell = None
            self._cache_shell_ts = now

        if self._cache_shell:
            try:
                b_layout = self._cache_shell.get("bar", {}).get("layout", {})
                for section in ["left", "center", "right"]:
                    if any(isinstance(it, dict) and it.get("id") == "com.kirulab.opendictate" for it in b_layout.get(section, [])):
                        bar_pos = section
                        break
            except Exception:
                pass
```

#### `opendictate-daemon.py` — Antes (línea 339)
```python
            "reserved_session": getattr(self, "reserved_dbus_session", None),
            "app_profiles": self.config_manager.get_all_app_profiles(),
            "open_windows": get_open_windows_list(),
```

#### `opendictate-daemon.py` — Después
```python
        if now - self._cache_profiles_ts > 3.0:
            self._cache_profiles = self.config_manager.get_all_app_profiles()
            self._cache_profiles_ts = now
        if now - self._cache_windows_ts > 3.0:
            self._cache_windows = get_open_windows_list()
            self._cache_windows_ts = now

        state_data = {
            "state": self.state,
            # ... resto del diccionario state_data permanece igual hasta bar_position ...
            "bar_position": bar_pos,
            "reserved_session": getattr(self, "reserved_dbus_session", None),
            "app_profiles": self._cache_profiles,
            "open_windows": self._cache_windows,
```
*(Nota: Para el bloque final se asume la reestructuración al construir `state_data` reemplazando las funciones de lectura directa por las variables cacheadas)*.

### Verificación
```bash
grep -n 'get_open_windows_list\|get_all_app_profiles\|shell.json' opendictate-daemon.py
```

---

## TAREA-08 — Robustecer lectura IPC — reemplazar `recv(1024)` por bucle hasta EOF

**Hallazgo:** CRIT-05 | **Severidad:** Alta | **Prerrequisito:** Ninguno

### Contexto
El servidor de sockets IPC actual lee un único chunk arbitrario de 1024 bytes truncando los mensajes JSON largos. Esto daña estructuras IPC como `save-profile: { ... }` cuando son extensas.

### Archivos a modificar
- `core/ipc.py`

### Cambio requerido

#### `core/ipc.py` — Antes (línea 46)
```python
                    conn.settimeout(0.5)
                    data = conn.recv(1024).decode('utf-8').strip()
```

#### `core/ipc.py` — Después
```python
                    conn.settimeout(0.5)
                    chunks = []
                    while True:
                        chunk = conn.recv(1024)
                        if not chunk:
                            break
                        chunks.append(chunk.decode('utf-8'))
                    data = "".join(chunks).strip()
```

### Verificación
```bash
python3 -c "from core.ipc import IPCServer; print('OK')"
```

---

## TAREA-09 — Mover socket IPC a `$XDG_RUNTIME_DIR`

**Hallazgo:** ID-DAEMON-16 | **Severidad:** Media | **Prerrequisito:** Ninguno

### Contexto
Actualmente, el socket de comunicación se crea rígidamente en `/tmp/opendictate.socket`, lo que puede entrar en conflicto en sistemas multi-usuario. Debe migrarse al directorio efímero `$XDG_RUNTIME_DIR`, preservando `/tmp` solo como fallback. 

### Archivos a modificar
- `core/ipc.py`
- `install.sh`
- `uninstall.sh`
- `core/updater.py`
- `gnome-extension/com.kirulab.opendictate@kirulab.com/extension.js`

### Cambio requerido

#### `core/ipc.py` — Antes (línea 12)
```python
SOCKET_PATH = "/tmp/opendictate.socket"
```

#### `core/ipc.py` — Después
```python
SOCKET_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "opendictate.socket")
```

#### `install.sh` — Antes (línea 134)
```bash
rm -f /tmp/opendictate.socket /tmp/opendictate_state.json*
```

#### `install.sh` — Después
```bash
rm -f "${XDG_RUNTIME_DIR:-/tmp}/opendictate.socket" /tmp/opendictate_state.json*
```

#### `uninstall.sh` — Antes (línea 46)
```bash
rm -f /tmp/opendictate.socket
```

#### `uninstall.sh` — Después
```bash
rm -f "${XDG_RUNTIME_DIR:-/tmp}/opendictate.socket"
```

#### `core/updater.py` — Antes (línea 368)
```python
        if os.path.exists("/tmp/opendictate.socket"):
            try:
                os.remove("/tmp/opendictate.socket")
```

#### `core/updater.py` — Después
```python
        socket_path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "opendictate.socket")
        if os.path.exists(socket_path):
            try:
                os.remove(socket_path)
```

#### `gnome-extension/com.kirulab.opendictate@kirulab.com/extension.js` — Antes (línea 13)
```javascript
const SOCKET_PATH = '/tmp/opendictate.socket';
```

#### `gnome-extension/com.kirulab.opendictate@kirulab.com/extension.js` — Después
```javascript
const GLib = imports.gi.GLib;
const SOCKET_PATH = GLib.getenv('XDG_RUNTIME_DIR') ? `${GLib.getenv('XDG_RUNTIME_DIR')}/opendictate.socket` : '/tmp/opendictate.socket';
```

### Verificación
```bash
grep -rn 'opendictate.socket' . --include='*.py' --include='*.sh' --include='*.js'
```

---

## TAREA-10 — Eliminar archivo de captura de pantalla tras upload en `core/llm.py`

**Hallazgo:** ID-DAEMON-15 | **Severidad:** Media | **Prerrequisito:** Ninguno

### Contexto
Cuando la visión de Gemini está activa, el pantallazo permanece colgado en el temporal tras haber sido transferido a la API. Se requiere que sea borrado de manera robusta y que también ocupe `$XDG_RUNTIME_DIR`.

### Archivos a modificar
- `core/llm.py`

### Cambio requerido

#### `core/llm.py` — Antes (línea 84)
```python
            if enable_vision:
                shot_path = "/tmp/dictate_vision.png"
                try:
                    from core.window_utils import capture_active_window_screenshot
                    if capture_active_window_screenshot(shot_path):
                        my_file = client.files.upload(file=shot_path)
                        prompt_parts.append("Below is a context image of the active application window:")
                        prompt_parts.append(my_file)
                        logging.info("Context screenshot attached successfully to LLM prompt.")
                except Exception as e:
                    logging.error(f"Error capturing or attaching window screenshot for vision: {e}")
```

#### `core/llm.py` — Después
```python
            if enable_vision:
                shot_path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "opendictate_vision.png")
                try:
                    from core.window_utils import capture_active_window_screenshot
                    if capture_active_window_screenshot(shot_path):
                        my_file = client.files.upload(file=shot_path)
                        prompt_parts.append("Below is a context image of the active application window:")
                        prompt_parts.append(my_file)
                        logging.info("Context screenshot attached successfully to LLM prompt.")
                except Exception as e:
                    logging.error(f"Error capturing or attaching window screenshot for vision: {e}")
                finally:
                    try:
                        if os.path.exists(shot_path):
                            os.unlink(shot_path)
                    except Exception:
                        pass
```

### Verificación
```bash
python3 -c "from core.llm import LLMService; print('OK')"
```

---

## TAREA-11 — Corregir precedencia de operadores en detección GPU NVIDIA (`core/hardware.py`)

**Hallazgo:** ID-DAEMON-14 | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
El script de detección evalúa de forma errónea la presencia de NVIDIA por la precedencia estricta del operador `and` por encima de `or`. Esto podría causar falsos positivos.

### Archivos a modificar
- `core/hardware.py`

### Cambio requerido

#### `core/hardware.py` — Antes (línea 118)
```python
                    if "vga" in line.lower() or "3d" in line.lower() and "nvidia" in line.lower():
```

#### `core/hardware.py` — Después
```python
                    if ("vga" in line.lower() or "3d" in line.lower()) and "nvidia" in line.lower():
```

### Verificación
```bash
# Test manual con strings de ejemplo
python3 -c 'line="Intel VGA"; print(("vga" in line.lower() or "3d" in line.lower()) and "nvidia" in line.lower())'
```

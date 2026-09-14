# Fase 1: Crashes Críticos y Errores Fatales (TAREA-01 a TAREA-06)

## TAREA-01 — Agregar `import time` en `core/config.py`

**Hallazgo de referencia:** CRIT-02 | **Severidad:** CRÍTICA | **Prerrequisito:** Ninguno

### Contexto
La función `_get_api_key_safe` en `core/config.py` utiliza `time.sleep(0.05)` en la línea ~121 en caso de fallos del keyring. Sin embargo, el módulo `time` nunca fue importado en la cabecera del archivo, lo que provoca un `NameError` fatal al intentar reintentar la obtención de la clave.

### Archivo a modificar
`/home/butcherwutcher/Projects/dev/dictate-whisper/core/config.py`

### Cambio requerido

#### Antes (línea 8)
```python
import os
import json
import sqlite3
import logging
```

#### Después
```python
import os
import json
import time
import sqlite3
import logging
```

### Verificación
```bash
python3 -c "from core.config import ConfigManager; print('OK')"
```

---

## TAREA-02 — Corregir ImportError en `ui/wizard_tui.py`

**Hallazgo de referencia:** CRIT-03 | **Severidad:** CRÍTICA | **Prerrequisito:** Ninguno

### Contexto
El asistente de terminal (`ui/wizard_tui.py`) intenta importar y utilizar una función inexistente llamada `get_system_hardware_info` desde `core.hardware`. La función correcta que provee este diccionario es `get_gpu_info()`. Adicionalmente, el diccionario retornado usa la clave `cuda_ready` en lugar de `has_cuda`.

### Archivo a modificar
`/home/butcherwutcher/Projects/dev/dictate-whisper/ui/wizard_tui.py`

### Cambio requerido

#### Antes (línea 38)
```python
from core.hardware import get_system_hardware_info
```

#### Después
```python
from core.hardware import get_gpu_info
```

#### Antes (línea 229)
```python
        self.hw_info = get_system_hardware_info()
```

#### Después
```python
        self.hw_info = get_gpu_info()
```

#### Antes (línea 259)
```python
                        gpu_text = f"GPU: {self.hw_info.get('gpu_name', 'No detectada')} | CUDA: {'Disponible' if self.hw_info.get('has_cuda') else 'No'}"
```

#### Después
```python
                        gpu_text = f"GPU: {self.hw_info.get('gpu_name', 'No detectada')} | CUDA: {'Disponible' if self.hw_info.get('cuda_ready') else 'No'}"
```

### Verificación
```bash
python3 -c "import ui.wizard_tui; print('OK')"
```

---

## TAREA-03 — Corregir nombre de atributo IPC en `quit_app()`

**Hallazgo de referencia:** ID-DAEMON-13 | **Severidad:** ALTA | **Prerrequisito:** Ninguno

### Contexto
En `opendictate-daemon.py`, el servidor IPC se inicializa y se guarda en el atributo `self.ipc`. Sin embargo, al cerrar la aplicación, la función `quit_app()` intenta detener el servidor accediendo al atributo incorrecto `self.ipc_server`, lo que impide cerrar el socket limpiamente.

### Archivo a modificar
`/home/butcherwutcher/Projects/dev/dictate-whisper/opendictate-daemon.py`

### Cambio requerido

#### Antes (línea 539)
```python
            if hasattr(self, "ipc_server") and self.ipc_server:
                self.ipc_server.stop()
```

#### Después
```python
            if hasattr(self, "ipc") and self.ipc:
                self.ipc.stop()
```

### Verificación
Inspección visual del código.

---

## TAREA-04 — Corregir navegación del GTK Wizard (step vacío)

**Hallazgo de referencia:** ID-UI-09 | **Severidad:** ALTA | **Prerrequisito:** Ninguno

### Contexto
En versiones anteriores del GTK Wizard (`ui/wizard.py`), existía una página dedicada a "Voice Commands" en el paso 3. Esta página ya no se inicializa en la vista (`_build_ui`), pero las páginas subsiguientes (AI, Shortcuts, Bubble, Finish) siguen agregándose al `GtkStack` con los identificadores `step_4`, `step_5`, `step_6` y `step_7`. Esto genera un "hueco" en la navegación cuando el contador interno pide el `step_3`, dejando la ventana en blanco.

### Archivo a modificar
`/home/butcherwutcher/Projects/dev/dictate-whisper/ui/wizard.py`

### Cambio requerido

#### Antes (línea 750)
```python
        self.stack.add_named(scroll, "step_4")
```
#### Después
```python
        self.stack.add_named(scroll, "step_3")
```

#### Antes (línea 843)
```python
        self.stack.add_named(scroll, "step_5")
```
#### Después
```python
        self.stack.add_named(scroll, "step_4")
```

#### Antes (línea 997)
```python
        self.stack.add_named(scroll, "step_6")
```
#### Después
```python
        self.stack.add_named(scroll, "step_5")
```

#### Antes (línea 1114)
```python
        self.stack.add_named(scroll, "step_7")
```
#### Después
```python
        self.stack.add_named(scroll, "step_6")
```

### Verificación
```bash
python3 -c "from ui.wizard import FirstRunWizard; print('OK')"
```

---

## TAREA-05 — Implementar `_save_autostart()` en `FirstRunWizard`

**Hallazgo de referencia:** ID-UI-03 | **Severidad:** CRÍTICA | **Prerrequisito:** Ninguno

### Contexto
Al finalizar el asistente inicial (`ui/wizard.py:~1396`), se llama al método `self._save_autostart()` para crear el archivo `.desktop` de inicio automático. Sin embargo, este método no fue implementado en la clase `FirstRunWizard`, provocando un `AttributeError` justo en el último paso que impide guardar toda la configuración.

### Archivo a modificar
`/home/butcherwutcher/Projects/dev/dictate-whisper/ui/wizard.py`

### Cambio requerido

#### Antes (línea 1323)
```python
    def _save_and_close(self) -> None:
```

#### Después
```python
    def _save_autostart(self) -> None:
        """Create or remove the autostart .desktop file based on switch state."""
        autostart_dir = os.path.expanduser("~/.config/autostart")
        autostart_path = os.path.join(autostart_dir, "opendictate.desktop")
        
        if hasattr(self, "autostart_switch") and self.autostart_switch.get_active():
            os.makedirs(autostart_dir, exist_ok=True)
            home = os.path.expanduser("~")
            content = f"""[Desktop Entry]
Type=Application
Name=OpenDictate
Exec={home}/.local/share/opendictate/.venv/bin/python {home}/.local/share/opendictate/opendictate-daemon.py --force-start
Icon={home}/.local/share/opendictate/img/logo.png
Terminal=false
Categories=Utility;AudioVideo;Accessibility;
X-GNOME-Autostart-enabled=true
"""
            with open(autostart_path, "w") as f:
                f.write(content)
        else:
            if os.path.exists(autostart_path):
                os.remove(autostart_path)

    def _save_and_close(self) -> None:
```

### Verificación
Inspección visual del código implementado.

---

## TAREA-06 — Eliminar definición duplicada de `_notify_daemon_reload`

**Hallazgo de referencia:** ID-UI-10 | **Severidad:** BAJA | **Prerrequisito:** Ninguno

### Contexto
En `opendictate_config_ui.py`, la función `_notify_daemon_reload` está definida dos veces. La primera (alrededor de la línea 1724) es la correcta y contiene lógica adicional para manejar un archivo de estado JSON. La segunda (alrededor de la línea 2459) es una definición duplicada incompleta al final de la clase, que sobrescribe a la primera y provoca pérdida de funcionalidad.

### Archivo a modificar
`/home/butcherwutcher/Projects/dev/dictate-whisper/opendictate_config_ui.py`

### Cambio requerido

#### Antes (líneas 2459 a 2471)
```python
    def _notify_daemon_reload(self) -> None:
        """Signal running daemon to reload config via Unix domain socket."""
        try:
            import socket
            from core.ipc import SOCKET_PATH
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(SOCKET_PATH)
            s.sendall(b"reload-config")
            s.close()
        except Exception:
            pass
```

#### Después
```python
    # (Definición de _notify_daemon_reload duplicada eliminada, se conserva la de la línea 1724)
```

### Verificación
```bash
grep -n '_notify_daemon_reload' opendictate_config_ui.py
# Debería mostrar exactamente 1 línea "def _notify_daemon_reload(self) -> None:"
```

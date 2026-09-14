# Auditoría de Tests, Documentación e Integración de GNOME

## TAREA-49 — Refactorizar `test_dbus_integration.py` para usar `unittest.TestCase` y `MagicMock`

**Hallazgo:** ID-TEST-01 | **Severidad:** Media | **Prerrequisito:** Ninguno

### Contexto
El archivo `tests/test_dbus_integration.py` está escrito como un script procedimental (`test_dbus_lifecycle()`) que intenta usar D-Bus de forma real sobre el bus de sesión, lo que falla en entornos CI (GitHub Actions) donde no hay un bus de sesión activo.

### Archivos a modificar / crear
- `tests/test_dbus_integration.py`

### Cambio requerido (Resumen del Diff)
Reemplazar la ejecución directa por una clase de tests con `unittest` aislando la llamada a `bus_get_sync`.

#### `tests/test_dbus_integration.py` — Antes (líneas 15-18)
```python
def test_dbus_lifecycle():
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    # -------------------------------------------------------------------------
```
#### `tests/test_dbus_integration.py` — Después
```python
import unittest
from unittest.mock import patch, MagicMock

class TestDBusIntegration(unittest.TestCase):
    @patch('gi.repository.Gio.bus_get_sync')
    def test_dbus_lifecycle(self, mock_bus_get):
        mock_bus = MagicMock()
        mock_bus_get.return_value = mock_bus
        # Configurar retorno simulado para GetStatus
        mock_res = MagicMock()
        mock_res.unpack.return_value = ['{"state": "IDLE"}']
        mock_bus.call_sync.return_value = mock_res
        
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        
        # Test 1: GetStatus
```

---

## TAREA-50 — Test de regresión para CRIT-02 y corrección de `import time` en `core/config.py`

**Hallazgo:** CRIT-02 | **Severidad:** Crítica | **Prerrequisito:** Fase 4 completa

### Contexto
El método `_get_api_key_safe` en `core/config.py` incluye un bucle de reintentos que usa `time.sleep(0.05)`, pero el módulo `time` no está importado, lo que provoca un `NameError` al fallar el anillo de claves (Keyring).

### Archivos a modificar / crear
- `core/config.py`
- `tests/test_core_config.py`

### Cambio requerido

#### `core/config.py` — Antes (líneas 8-13)
```python
import os
import json
import sqlite3
import logging
from typing import Dict, Any, Optional, Tuple, List

try:
```
#### `core/config.py` — Después
```python
import os
import time
import json
import sqlite3
import logging
from typing import Dict, Any, Optional, Tuple, List

try:
```

#### `tests/test_core_config.py` — Añadir nuevo test
```python
    @unittest.mock.patch('core.config.keyring')
    def test_get_api_key_safe_retry(self, mock_keyring):
        mock_keyring.get_password.side_effect = Exception("Keyring failure")
        # Esto fallaría por NameError si no hay "import time" en config.py
        key = self.config_manager._get_api_key_safe()
        self.assertEqual(key, "")
```

---

## TAREA-51 — Test de regresión para CRIT-05 y aumento de payload en `core/ipc.py`

**Hallazgo:** CRIT-05 | **Severidad:** Media | **Prerrequisito:** Ninguno

### Contexto
En `core/ipc.py`, se leen comandos con `conn.recv(1024)`. Comandos largos como `set-config system_prompt:...` que contengan prompts grandes (para la IA) pueden verse truncados.

### Archivos a modificar / crear
- `core/ipc.py`

### Cambio requerido

#### `core/ipc.py` — Antes (línea 47)
```python
                    conn.settimeout(0.5)
                    data = conn.recv(1024).decode('utf-8').strip()
                finally:
```
#### `core/ipc.py` — Después
```python
                    conn.settimeout(0.5)
                    data = conn.recv(4096).decode('utf-8').strip()
                finally:
```

---

## TAREA-52 — Test de importación de `ui/wizard_tui.py`

**Hallazgo:** ID-TEST-04 | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
`ui/wizard_tui.py` usa `textual`. Se requiere asegurar que se importe correctamente sin fallos de sintaxis en CI.

### Archivos a modificar / crear
- Crear `tests/test_wizard_tui.py`

### Cambio requerido
Añadir test simple:
```python
import unittest

class TestWizardTUI(unittest.TestCase):
    def test_import_wizard(self):
        try:
            import ui.wizard_tui
            self.assertIsNotNone(ui.wizard_tui.WizardTUI)
        except ImportError as e:
            self.fail(f"Fallo al importar wizard_tui: {e}")
```

---

## TAREA-53 — Corregir ejemplo de `nc` en la Especificación IPC

**Hallazgo:** DOC-01 | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
El archivo `docs/IPC_PROTOCOL_SPECIFICATION.md` usa la bandera `-u` (UDP) con netcat para comunicarse con un Unix Domain Socket de tipo `SOCK_STREAM` (TCP-like). Esto causa error de protocolo.

### Archivos a modificar / crear
- `docs/IPC_PROTOCOL_SPECIFICATION.md`

### Cambio requerido

#### `docs/IPC_PROTOCOL_SPECIFICATION.md` — Antes (línea 334)
```bash
echo "record" | nc -U -u -q 0 /tmp/opendictate.socket
```
#### `docs/IPC_PROTOCOL_SPECIFICATION.md` — Después
```bash
echo "record" | nc -U -q 0 /tmp/opendictate.socket
```

---

## TAREA-54 — Actualizar catálogo de comandos IPC en Especificación

**Hallazgo:** DOC-02 | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
Falta mencionar comandos recientes agregados al IPC en `docs/IPC_PROTOCOL_SPECIFICATION.md`.

### Archivos a modificar / crear
- `docs/IPC_PROTOCOL_SPECIFICATION.md`

### Cambio requerido (Añadir a la lista en línea 326+)
Añadir a los comandos documentados:
```markdown
* `quit`: Detiene y cierra el daemon completamente.
* `reload-config`: Recarga los perfiles de configuración desde la base de datos.
```

---

## TAREA-55 — Actualizar `TECHNICAL_DEBT.md` y `CHANGELOG.md`

*(Placeholder para reflejar todas las correcciones ejecutadas durante la Fase 5)*

---

## TAREA-56 — Corregir parámetro `GLib.Bytes` en extensión de GNOME

**Hallazgo:** CRIT-GNOME-01 | **Severidad:** Crítica | **Prerrequisito:** Ninguno

### Contexto
En GJS moderno (GNOME 45+), `new GLib.Bytes(cmd)` donde `cmd` es un string (UTF-16 interno) a menudo falla porque espera un `Uint8Array`. Se debe usar `ByteArray` o `TextEncoder`.

### Archivos a modificar / crear
- `gnome-extension/com.kirulab.opendictate@kirulab.com/extension.js`

### Cambio requerido

#### `gnome-extension/.../extension.js` — Antes (líneas 347-348)
```javascript
                    let output = connection.get_output_stream();
                    output.write_bytes_async(new GLib.Bytes(cmd), GLib.PRIORITY_DEFAULT, null, (stream, res2) => {
```
#### `gnome-extension/.../extension.js` — Después
```javascript
                    let output = connection.get_output_stream();
                    let encoder = new TextEncoder();
                    output.write_bytes_async(new GLib.Bytes(encoder.encode(cmd)), GLib.PRIORITY_DEFAULT, null, (stream, res2) => {
```

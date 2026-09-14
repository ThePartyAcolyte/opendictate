# Auditoría de Código Muerto y Limpieza

## TAREA-21 — Eliminar `patch_changelog.py`

**Hallazgo:** Archivo parche temporal. | **Severidad:** Baja | **Prerrequisito:** Fase 3

### Contexto
El script `patch_changelog.py` fue creado de forma temporal para integrar la actualización del changelog de Herder. Ya cumplió su propósito y puede ser eliminado.

### Archivos a modificar
- `patch_changelog.py`

### Cambios requeridos
Acción: Eliminar el archivo del repositorio.
```bash
git rm patch_changelog.py
```

### Verificación
```bash
ls patch_changelog.py
```

## TAREA-22 — Eliminar `patch_window_utils.py`

**Hallazgo:** Archivo parche temporal. | **Severidad:** Baja | **Prerrequisito:** Fase 3

### Contexto
El script `patch_window_utils.py` fue utilizado para inyectar las funciones relacionadas a Herder en `core/window_utils.py`. Las funciones ya están integradas.

### Archivos a modificar
- `patch_window_utils.py`

### Cambios requeridos
Acción: Eliminar el archivo.
```bash
git rm patch_window_utils.py
```

### Verificación
```bash
ls patch_window_utils.py
```

## TAREA-23 — Eliminar `i18n.py` (raíz) y actualizar referencias

**Hallazgo:** Módulo redundante en raíz. | **Severidad:** Media | **Prerrequisito:** Fase 3

### Contexto
El archivo `i18n.py` en la raíz es un puente redundante hacia el paquete `i18n/__init__.py`. Se debe eliminar y limpiar las referencias en los scripts de empaquetado e instalación.

### Archivos a modificar
- `i18n.py`
- `install.sh`
- `packaging/build_arch.sh`
- `packaging/build_deb.sh`

### Cambios requeridos

#### `i18n.py`
Acción: Eliminar el archivo.
```bash
git rm i18n.py
```

#### `install.sh` — Antes
```bash
cp launch_wizard.py "$INSTALL_DIR/"
cp i18n.py "$INSTALL_DIR/"
cp -r i18n "$INSTALL_DIR/"
```
#### `install.sh` — Después
```bash
cp launch_wizard.py "$INSTALL_DIR/"
cp -r i18n "$INSTALL_DIR/"
```

#### `packaging/build_arch.sh` — Antes
```bash
cp launch_wizard.py "${PKG_DIR}/opt/opendictate/"
cp i18n.py "${PKG_DIR}/opt/opendictate/"
cp -r i18n "${PKG_DIR}/opt/opendictate/"
```
#### `packaging/build_arch.sh` — Después
```bash
cp launch_wizard.py "${PKG_DIR}/opt/opendictate/"
cp -r i18n "${PKG_DIR}/opt/opendictate/"
```

#### `packaging/build_deb.sh` — Antes
```bash
cp launch_wizard.py "${PKG_DIR}/opt/opendictate/"
cp i18n.py "${PKG_DIR}/opt/opendictate/"
cp -r i18n "${PKG_DIR}/opt/opendictate/"
```
#### `packaging/build_deb.sh` — Después
```bash
cp launch_wizard.py "${PKG_DIR}/opt/opendictate/"
cp -r i18n "${PKG_DIR}/opt/opendictate/"
```

### Verificación
```bash
grep -rn 'cp i18n.py' .
```

## TAREA-24 — Eliminar métodos de comandos de voz en `ui/wizard.py`

**Hallazgo:** Bloques huérfanos. | **Severidad:** Baja | **Prerrequisito:** Fase 3

### Contexto
Los métodos relacionados a comandos de voz interactivos en el Wizard fueron deprecados o movidos en refactorizaciones. Deben ser eliminados completamente.

### Archivos a modificar
- `ui/wizard.py`

### Cambios requeridos
Acción: Eliminar los siguientes bloques de código completos:
- `_build_page_voice_commands` (Líneas 511-636)
- `_record_wizard_sample` (Líneas 1164-1193)
- `_clear_wizard_sample` (Líneas 1195-1200)
- `_on_wizard_calibrate_aec` (Líneas 1202-1219)
- `_on_wizard_calibrate_noise` (Líneas 1221-1290)

### Verificación
```bash
python3 -c "from ui.wizard import FirstRunWizard; print('OK')"
```

## TAREA-25 — Eliminar `get_trailing_silence_duration` en `core/vad.py`

**Hallazgo:** Función huérfana. | **Severidad:** Baja | **Prerrequisito:** Fase 3

### Contexto
La función `get_trailing_silence_duration` no se utiliza en el proyecto y debe removerse.

### Archivos a modificar
- `core/vad.py`

### Cambios requeridos

#### `core/vad.py` — Antes
```python
    def get_trailing_silence_duration(self, current_audio_time: float) -> float:
        """Return the current ongoing silence duration in seconds."""
        if self.current_silence_start is not None:
            return max(0.0, current_audio_time - self.current_silence_start)
        if self.last_speech_time > 0.0:
            return max(0.0, current_audio_time - self.last_speech_time)
        return 0.0
```
#### `core/vad.py` — Después
Eliminar el bloque completo.

### Verificación
```bash
grep -rn 'get_trailing_silence_duration' . --include='*.py'
```

## TAREA-26 — Eliminar stub duplicado de `_streaming_transcriber_loop` en `opendictate-daemon.py`

**Hallazgo:** Stub duplicado incompleto. | **Severidad:** Media | **Prerrequisito:** Fase 3

### Contexto
Existen dos declaraciones de `_streaming_transcriber_loop` en el archivo principal del daemon. El primer stub está incompleto y sobreescrito por la implementación final más adelante, por lo que debe eliminarse.

### Archivos a modificar
- `opendictate-daemon.py`

### Cambios requeridos

#### `opendictate-daemon.py` — Antes (Líneas 865-870)
```python
    def _streaming_transcriber_loop(self) -> None:
        """Adaptive VAD-based transcription and silence-gated tail voice command worker loop."""
        bytes_per_sec = 16000 * 2
        last_vad_byte_offset = 0
        last_checked_speech_end = -1.0
```
#### `opendictate-daemon.py` — Después
Eliminar el bloque.

### Verificación
```bash
grep -n 'def _streaming_transcriber_loop' opendictate-daemon.py
```
(Debe mostrar 1 resultado).

## TAREA-27 — Documentar `parse_verbal_punctuation` como TD-002 en `TECHNICAL_DEBT.md`

**Hallazgo:** Función implementada pero desconectada. | **Severidad:** Informativa | **Prerrequisito:** Ninguno

### Contexto
La función `parse_verbal_punctuation` en `core/engine.py` está lista pero no integrada al flujo. Debe registrarse como deuda técnica.

### Archivos a modificar
- `TECHNICAL_DEBT.md`

### Cambios requeridos
Agregar al archivo `TECHNICAL_DEBT.md`:
```markdown
### TD-002: Conectar `parse_verbal_punctuation` al pipeline de transcripción
- **Archivo:** `core/engine.py:220-251`
- **Estado:** Implementada y testeada, pero no conectada al pipeline
- **Trabajo pendiente:** Requiere (1) catálogo multilingüe de frases por idioma, (2) UI de configuración para activar/desactivar, (3) integración en el pipeline de salida de texto
```

### Verificación
```bash
cat TECHNICAL_DEBT.md
```

## TAREA-28 — Limpieza de imports en `core/engine.py`

**Hallazgo:** Imports no usados. | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
Módulos importados que no son consumidos por el código.

### Archivos a modificar
- `core/engine.py`

### Cambios requeridos

#### `core/engine.py` — Antes
```python
import re
import time
import logging
import threading
import numpy as np
from typing import Dict, Any, Optional, Tuple, Callable, List
```
#### `core/engine.py` — Después
```python
import re
import logging
import threading
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
```

### Verificación
```bash
python3 -c "import core.engine; print('OK')"
```

## TAREA-29 — Limpieza de imports en `core/llm.py`

**Hallazgo:** Imports no usados. | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
Módulos no utilizados en LLM.

### Archivos a modificar
- `core/llm.py`

### Cambios requeridos

#### `core/llm.py` — Antes
```python
import os
import time
import subprocess
import logging
from typing import Dict, Any, Optional, Callable
from core.config import ConfigManager
```
#### `core/llm.py` — Después
```python
import logging
from typing import Dict, Any, Optional, Callable
from core.config import ConfigManager
```

### Verificación
```bash
python3 -c "import core.llm; print('OK')"
```

## TAREA-30 — Limpieza de imports en `core/dbus_service.py`

**Hallazgo:** Imports no usados. | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
Módulo no utilizado.

### Archivos a modificar
- `core/dbus_service.py`

### Cambios requeridos

#### `core/dbus_service.py` — Antes
```python
import json
import logging
import uuid
from typing import Any, Callable, Dict, Optional
```
#### `core/dbus_service.py` — Después
```python
import json
import logging
from typing import Any, Callable, Dict, Optional
```

### Verificación
```bash
python3 -c "import core.dbus_service; print('OK')"
```

## TAREA-31 — Limpieza de imports en `opendictate-daemon.py`

**Hallazgo:** Imports no usados. | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
Módulo `Gdk` importado sin uso.

### Archivos a modificar
- `opendictate-daemon.py`

### Cambios requeridos

#### `opendictate-daemon.py` — Antes
```python
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
```
#### `opendictate-daemon.py` — Después
```python
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
```

### Verificación
```bash
python3 -c "import opendictate-daemon; print('OK')"
```

## TAREA-32 — Limpieza de imports en `core/aec.py`

**Hallazgo:** Imports no usados. | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
Módulos no utilizados en AEC.

### Archivos a modificar
- `core/aec.py`

### Cambios requeridos

#### `core/aec.py` — Antes
```python
import os
import math
import struct
import subprocess
import tempfile
import time
import logging
from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any, List, Tuple
```
#### `core/aec.py` — Después
```python
import os
import struct
import subprocess
import tempfile
import time
import logging
from dataclasses import dataclass
from typing import Optional, Callable, Tuple
```

### Verificación
```bash
python3 -c "import core.aec; print('OK')"
```

## TAREA-33 — Limpieza de imports en `plugin.py`

**Hallazgo:** Imports no usados y duplicados. | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
En el plugin SD.

### Archivos a modificar
- `plugins/com.kirulab.opendictate.sdplugin/plugin.py`

### Cambios requeridos

#### `plugins/com.kirulab.opendictate.sdplugin/plugin.py` — Antes
```python
import asyncio
import websockets
import subprocess
import os
import signal
import base64
import time
import math
import shutil
from PIL import Image, ImageDraw
import logging

logging.basicConfig(filename='/tmp/opendictate_plugin.log', level=logging.DEBUG, 
                    format='%(asctime)s %(levelname)s: %(message)s')
import io
import base64
```
#### `plugins/com.kirulab.opendictate.sdplugin/plugin.py` — Después
```python
import asyncio
import websockets
import subprocess
import os
import time
import math
import shutil
from PIL import Image, ImageDraw
import logging

logging.basicConfig(filename='/tmp/opendictate_plugin.log', level=logging.DEBUG, 
                    format='%(asctime)s %(levelname)s: %(message)s')
import io
import base64
```

### Verificación
```bash
python3 -c "import plugins.com_kirulab_opendictate_sdplugin.plugin; print('OK')"
```

## TAREA-34 — Mover imports inline al nivel de módulo en `core/window_utils.py`

**Hallazgo:** Imports redundantes inline. | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
Módulos que ya están importados o deben importarse a nivel de cabecera en lugar de inline. (json está en cabecera. os no, pero limpiaremos el inline os/socket).

### Archivos a modificar
- `core/window_utils.py`

### Cambios requeridos

#### `core/window_utils.py` — Antes (Línea 139)
```python
    import os, socket
```
#### `core/window_utils.py` — Después (Línea 139)
```python
    import socket
```
*(Nota: Añadir `import os` a la cabecera del archivo si no está).*

#### `core/window_utils.py` — Antes (Línea 396)
```python
    import json
```
#### `core/window_utils.py` — Después (Línea 396)
Eliminar la línea.

#### `core/window_utils.py` — Antes (Línea 432)
```python
    import json
```
#### `core/window_utils.py` — Después (Línea 432)
Eliminar la línea.

### Verificación
```bash
python3 -c "from core.window_utils import get_open_windows_list; print('OK')"
```

## TAREA-35 — Eliminar claves i18n huérfanas

**Hallazgo:** Claves de traducciones no usadas. | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
Claves de idioma que ya no tienen referencia en el código.

### Archivos a modificar
- `i18n/en.py`
- `i18n/es.py`
- `i18n/de.py`
- `i18n/fr.py`

### Cambios requeridos

Eliminar las líneas correspondientes a las claves `lbl_chunk_stride`, `lbl_chunk_overlap`, `lbl_chunk_tolerance`, `wizard_step_voice_commands`, `wizard_voice_title`, `wizard_voice_subtitle` en los 4 archivos. (Generalmente se encuentran en las líneas 76-78 y 369-371).

### Verificación
```bash
grep -rn 'lbl_chunk_stride\|wizard_step_voice_commands' i18n/
```

## TAREA-12 — Definir `$OPENDECK_PLUGINS_DIR` en `install.sh`

**Hallazgo:** CRIT-04 | **Severidad:** Alta | **Prerrequisito:** Ninguno

### Contexto
En el script de instalación se utiliza la variable `$OPENDECK_PLUGINS_DIR` sin haber sido inicializada previamente en el bloque de variables, impidiendo la correcta instalación del plugin de OpenDeck en su carpeta.

### Archivos a modificar
- `install.sh`

### Cambio requerido

#### `install.sh` — Antes (línea 4)
```bash
INSTALL_DIR="$HOME/.local/share/opendictate"
VENV_DIR="$INSTALL_DIR/.venv"
OMARCHY_PLUGINS_DIR="$HOME/.config/omarchy/plugins"
GNOME_EXT_DIR="$HOME/.local/share/gnome-shell/extensions/com.kirulab.opendictate@kirulab.com"
```

#### `install.sh` — Después
```bash
INSTALL_DIR="$HOME/.local/share/opendictate"
VENV_DIR="$INSTALL_DIR/.venv"
OMARCHY_PLUGINS_DIR="$HOME/.config/omarchy/plugins"
GNOME_EXT_DIR="$HOME/.local/share/gnome-shell/extensions/com.kirulab.opendictate@kirulab.com"
OPENDECK_PLUGINS_DIR="$HOME/.config/opendeck/plugins"
```

### Verificación
```bash
bash -n install.sh && echo 'Sintaxis OK'
```

---

## TAREA-13 — Agregar `chmod +x` para `opendictate_config_ui.py` en `install.sh`

**Hallazgo:** ID-INFRA-07 | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
El binario del TUI de configuración se está copiando pero no se le otorgan permisos de ejecución (x), lo que puede romper invocaciones directas.

### Archivos a modificar
- `install.sh`

### Cambio requerido

#### `install.sh` — Antes (línea 112)
```bash
chmod +x "$INSTALL_DIR/opendictate-daemon.py"
chmod +x "$INSTALL_DIR/opendictate-client.py"
chmod +x "$INSTALL_DIR/launch_wizard.py"
```

#### `install.sh` — Después
```bash
chmod +x "$INSTALL_DIR/opendictate-daemon.py"
chmod +x "$INSTALL_DIR/opendictate-client.py"
chmod +x "$INSTALL_DIR/launch_wizard.py"
chmod +x "$INSTALL_DIR/opendictate_config_ui.py"
```

### Verificación
```bash
# Después de instalar
ls -la ~/.local/share/opendictate/opendictate_config_ui.py
```

---

## TAREA-14 — `install.sh` debe usar `-r requirements.txt`

**Hallazgo:** ID-INFRA-10 | **Severidad:** Media | **Prerrequisito:** Ninguno

### Contexto
El script listaba manualmente los paquetes Python de manera "hardcodeada". Debe derivarse del `requirements.txt` oficial.

### Archivos a modificar
- `install.sh`

### Cambio requerido

#### `install.sh` — Antes (línea 99)
```bash
uv pip install faster-whisper google-genai pycairo keyring textual numpy --python "$VENV_DIR"
```

#### `install.sh` — Después
```bash
uv pip install -r requirements.txt --python "$VENV_DIR"
```

### Verificación
```bash
bash -n install.sh && echo 'OK'
```

---

## TAREA-15 — Agregar `websockets` y `Pillow` a `requirements.txt`

**Hallazgo:** ID-INFRA-09 | **Severidad:** Media | **Prerrequisito:** Ninguno

### Contexto
El plugin del stream deck requiere `websockets` y `Pillow` para funcionar, pero faltan en las dependencias.

### Archivos a modificar
- `requirements.txt`

### Cambio requerido

#### `requirements.txt` — Antes (línea 1)
```text
faster-whisper
google-genai>=2.20.0
pycairo
keyring
numpy
textual
```

#### `requirements.txt` — Después
```text
faster-whisper
google-genai>=2.20.0
pycairo
keyring
numpy
textual
websockets
Pillow
```

### Verificación
```bash
cat requirements.txt | grep -E 'websockets|Pillow'
```

---

## TAREA-16 — `build_deb.sh` postinst — incluir dependencias adicionales

**Hallazgo:** ID-INFRA-11 | **Severidad:** Media | **Prerrequisito:** Ninguno

### Contexto
Las distribuciones paquetizadas no instalan las nuevas bibliotecas de UI/Deck por defecto.

### Archivos a modificar
- `packaging/build_deb.sh`

### Cambio requerido

#### `packaging/build_deb.sh` — Antes (líneas 146 y 153)
```bash
    uv pip install faster-whisper google-genai pycairo keyring --python "$VENV_DIR" || true
# ... más adelante ...
    "$VENV_DIR/bin/pip" install faster-whisper google-genai pycairo keyring || true
```

#### `packaging/build_deb.sh` — Después
```bash
    uv pip install faster-whisper google-genai pycairo keyring textual numpy websockets Pillow --python "$VENV_DIR" || true
# ... más adelante ...
    "$VENV_DIR/bin/pip" install faster-whisper google-genai pycairo keyring textual numpy websockets Pillow || true
```

### Verificación
```bash
bash -n packaging/build_deb.sh && echo 'OK'
```

---

## TAREA-17 — `build_arch.sh` post_install — crear venv e instalar dependencias

**Hallazgo:** ID-INFRA-12 | **Severidad:** Media | **Prerrequisito:** Ninguno

### Contexto
El `.PKGINFO` de arch carece del código para inicializar el entorno `uv` en su paso `post_install()`.

### Archivos a modificar
- `packaging/build_arch.sh`

### Cambio requerido

#### `packaging/build_arch.sh` — Antes (línea 121)
```bash
cat > "${BUILD_DIR}/opendictate.install" << 'INSTALL_EOF'
post_install() {
    echo "🐍 Configurando entorno para OpenDictate..."
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database -q || true
    fi
    if command -v gtk-update-icon-cache &> /dev/null; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
    echo "✔ Para inicializar el asistente ejecuta: opendictate --wizard"
    echo "✔ Para iniciar el servicio ejecuta: opendictate --daemon &"
}
```

#### `packaging/build_arch.sh` — Después
```bash
cat > "${BUILD_DIR}/opendictate.install" << 'INSTALL_EOF'
post_install() {
    echo "🐍 Configurando entorno para OpenDictate..."
    VENV_DIR="/opt/opendictate/.venv"
    if ! command -v uv &> /dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh || true
        export PATH="$HOME/.cargo/bin:/root/.cargo/bin:$PATH"
    fi
    
    if command -v uv &> /dev/null; then
        uv venv --system-site-packages --python /usr/bin/python3 "$VENV_DIR" || true
        uv pip install faster-whisper google-genai pycairo keyring textual numpy websockets Pillow --python "$VENV_DIR" || true
        if command -v nvidia-smi &> /dev/null || (command -v lspci &> /dev/null && lspci | grep -iq nvidia); then
            uv pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 --python "$VENV_DIR" || true
        fi
    else
        python3 -m venv --system-site-packages "$VENV_DIR" || true
        "$VENV_DIR/bin/pip" install faster-whisper google-genai pycairo keyring textual numpy websockets Pillow || true
        if command -v nvidia-smi &> /dev/null || (command -v lspci &> /dev/null && lspci | grep -iq nvidia); then
            "$VENV_DIR/bin/pip" install nvidia-cublas-cu12 nvidia-cudnn-cu12 || true
        fi
    fi

    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database -q || true
    fi
    if command -v gtk-update-icon-cache &> /dev/null; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
    echo "✔ Para inicializar el asistente ejecuta: opendictate --wizard"
    echo "✔ Para iniciar el servicio ejecuta: opendictate --daemon &"
}
```

### Verificación
```bash
bash -n packaging/build_arch.sh && echo 'OK'
```

---

## TAREA-18 — `uninstall.sh` — limpiar plugin Omarchy Shell y `shell.json`

**Hallazgo:** ID-INFRA-08 | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
El desinstalador ignora el plugin visual de Omarchy, dejando código y configuraciones huérfanas en el desktop del usuario.

### Archivos a modificar
- `uninstall.sh`

### Cambio requerido

#### `uninstall.sh` — Antes (línea 36)
```bash
echo "🧩 Desinstalando extensión GNOME Shell..."
gnome-extensions disable com.kirulab.opendictate@kirulab.com 2>/dev/null || true
rm -rf "$HOME/.local/share/gnome-shell/extensions/com.kirulab.opendictate@kirulab.com"

echo "📦 Eliminando plugins de OpenDeck..."
```

#### `uninstall.sh` — Después
```bash
echo "🧩 Desinstalando extensión GNOME Shell..."
gnome-extensions disable com.kirulab.opendictate@kirulab.com 2>/dev/null || true
rm -rf "$HOME/.local/share/gnome-shell/extensions/com.kirulab.opendictate@kirulab.com"

echo "🪄 Eliminando plugin de Omarchy Shell..."
rm -rf "$HOME/.config/omarchy/plugins/com.kirulab.opendictate"
if [ -f "$HOME/.config/omarchy/shell.json" ]; then
    python3 -c '
import json, os
p = os.path.expanduser("~/.config/omarchy/shell.json")
try:
    with open(p, "r") as f: d = json.load(f)
    for s in ["left", "center", "right"]:
        if "bar" in d and "layout" in d["bar"] and s in d["bar"]["layout"]:
            d["bar"]["layout"][s] = [i for i in d["bar"]["layout"][s] if not (isinstance(i, dict) and i.get("id") == "com.kirulab.opendictate")]
    with open(p, "w") as f: json.dump(d, f, indent=2)
except Exception: pass
' || true
fi

echo "📦 Eliminando plugins de OpenDeck..."
```

### Verificación
```bash
bash -n uninstall.sh && echo 'OK'
```

---

## TAREA-19 — `plugins/start.sh` — usar Python del venv

**Hallazgo:** ID-INFRA-13 | **Severidad:** Media | **Prerrequisito:** Ninguno

### Contexto
El ejecutable del Stream Deck llamaba al Python global, fallando cuando le hacían falta los paquetes `websockets` del VENV.

### Archivos a modificar
- `plugins/com.kirulab.opendictate.sdplugin/start.sh`

### Cambio requerido

#### `plugins/com.kirulab.opendictate.sdplugin/start.sh` — Antes (línea 2)
```bash
python3 plugin.py "$@"
```

#### `plugins/com.kirulab.opendictate.sdplugin/start.sh` — Después
```bash
VENV_PYTHON="$HOME/.local/share/opendictate/.venv/bin/python"
if [ -f "/opt/opendictate/.venv/bin/python" ]; then
    VENV_PYTHON="/opt/opendictate/.venv/bin/python"
fi

if [ -f "$VENV_PYTHON" ]; then
    "$VENV_PYTHON" plugin.py "$@"
else
    python3 plugin.py "$@"
fi
```

### Verificación
```bash
# Test manual
```

---

## TAREA-20 — `install.sh` — agregar `~/.local/bin` al PATH tras instalar `uv`

**Hallazgo:** ID-INFRA-18 | **Severidad:** Baja | **Prerrequisito:** Ninguno

### Contexto
`uv` puede instalarse en `~/.local/bin` en lugar de `~/.cargo/bin`, si no se actualiza el PATH, la compilación puede fallar de inmediato si no se detecta la herramienta.

### Archivos a modificar
- `install.sh`

### Cambio requerido

#### `install.sh` — Antes (línea 94)
```bash
        export PATH="$HOME/.cargo/bin:$PATH"
```

#### `install.sh` — Después
```bash
        export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
```

### Verificación
```bash
bash -n install.sh && echo 'OK'
```

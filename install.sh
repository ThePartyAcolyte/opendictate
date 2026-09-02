#!/bin/bash
set -e

INSTALL_DIR="$HOME/.local/share/opendictate"
VENV_DIR="$INSTALL_DIR/.venv"
OMARCHY_PLUGINS_DIR="$HOME/.config/omarchy/plugins"
GNOME_EXT_DIR="$HOME/.local/share/gnome-shell/extensions/com.kirulab.opendictate@kirulab.com"

echo "🚀 Instalando / Actualizando OpenDictate en $INSTALL_DIR..."

mkdir -p "$INSTALL_DIR"
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/share/applications"

echo "📄 Copiando archivos de la aplicación..."
if [ -d "$INSTALL_DIR" ]; then
    echo "🧹 Limpiando archivos de código fuente previos..."
    find "$INSTALL_DIR" -maxdepth 1 -type f -name "*.py" -delete
    rm -rf "$INSTALL_DIR/core" "$INSTALL_DIR/ui" "$INSTALL_DIR/plugins" "$INSTALL_DIR/img" "$INSTALL_DIR/i18n"
fi
mkdir -p "$INSTALL_DIR"
cp opendictate-daemon.py "$INSTALL_DIR/"
cp opendictate-client.py "$INSTALL_DIR/"
cp opendictate_config_ui.py "$INSTALL_DIR/"
cp launch_wizard.py "$INSTALL_DIR/"
cp i18n.py "$INSTALL_DIR/"
cp -r i18n "$INSTALL_DIR/"
cp -r core "$INSTALL_DIR/"
cp -r ui "$INSTALL_DIR/"
cp -r plugins "$INSTALL_DIR/"
cp -r img "$INSTALL_DIR/"

if [ -d "$HOME/.local/share/gnome-shell" ] || command -v gnome-shell &> /dev/null; then
    echo "🧩 Desplegando Extensión de GNOME Shell..."
    mkdir -p "$GNOME_EXT_DIR"
    cp -r gnome-extension/com.kirulab.opendictate@kirulab.com/* "$GNOME_EXT_DIR/"
    if command -v gnome-extensions &> /dev/null; then
        gnome-extensions disable "com.kirulab.opendictate@kirulab.com" 2>/dev/null || true
        sleep 0.5
        gnome-extensions enable "com.kirulab.opendictate@kirulab.com" 2>/dev/null || true
    fi
fi

if [ -d "$HOME/.config/omarchy" ]; then
    echo "🪄 Desplegando Plugin para Omarchy Shell..."
    mkdir -p "$OMARCHY_PLUGINS_DIR/com.kirulab.opendictate"
    rm -rf "$OMARCHY_PLUGINS_DIR/com.kirulab.opendictate"/*
    cp -r plugins/omarchy/opendictate/* "$OMARCHY_PLUGINS_DIR/com.kirulab.opendictate/"

    # Register in ~/.config/omarchy/shell.json if not present
    python3 - << 'PY_EOF'
import json, os
shell_path = os.path.expanduser("~/.config/omarchy/shell.json")
if os.path.exists(shell_path):
    try:
        with open(shell_path, "r") as f:
            data = json.load(f)
        bar = data.setdefault("bar", {}).setdefault("layout", {})
        exists = any(
            isinstance(item, dict) and item.get("id") == "com.kirulab.opendictate"
            for sec in ["left", "center", "right"]
            for item in bar.get(sec, [])
        )
        if not exists:
            # Insert at the beginning of the right section by default
            right = bar.setdefault("right", [])
            right.insert(0, {"id": "com.kirulab.opendictate"})
            with open(shell_path, "w") as f:
                json.dump(data, f, indent=2)
            print("  ✔ Widget com.kirulab.opendictate añadido a ~/.config/omarchy/shell.json")
    except Exception as e:
        print(f"  Advertencia: No se pudo auto-configurar shell.json: {e}")
PY_EOF

    if command -v omarchy-shell &> /dev/null; then
        omarchy-shell shell rescanPlugins 2>/dev/null || true
    fi
fi

if [ -d "$HOME/.config/opendeck" ]; then
    echo "📦 Desplegando Plugin para OpenDeck..."
    mkdir -p "$OPENDECK_PLUGINS_DIR"
    rm -rf "$OPENDECK_PLUGINS_DIR/com.kirulab.opendictate.sdplugin"
    cp -r plugins/com.kirulab.opendictate.sdplugin "$OPENDECK_PLUGINS_DIR/"
fi

echo "🐍 Verificando entorno virtual Python..."
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "Creando entorno virtual limpio..."
    rm -rf "$VENV_DIR"
    if ! command -v uv &> /dev/null; then
        echo "Instalando uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.cargo/bin:$PATH"
    fi
    uv venv --system-site-packages --python /usr/bin/python3 "$VENV_DIR"
fi

uv pip install faster-whisper google-genai pycairo keyring textual numpy --python "$VENV_DIR"

if command -v nvidia-smi &> /dev/null || (command -v lspci &> /dev/null && lspci | grep -iq nvidia); then
    echo "⚡ Tarjeta NVIDIA detectada. Instalando librerías de aceleración CUDA (cuBLAS / cuDNN)..."
    uv pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 --python "$VENV_DIR" || true
fi

echo "🔧 Configurando permisos y shebangs..."
sed -i "1s|.*|#!$VENV_DIR/bin/python|" "$INSTALL_DIR/opendictate-daemon.py"
sed -i "1s|.*|#!$VENV_DIR/bin/python|" "$INSTALL_DIR/opendictate-client.py"
sed -i "1s|.*|#!$VENV_DIR/bin/python|" "$INSTALL_DIR/opendictate_config_ui.py"
sed -i "1s|.*|#!$VENV_DIR/bin/python|" "$INSTALL_DIR/launch_wizard.py"

chmod +x "$INSTALL_DIR/opendictate-daemon.py"
chmod +x "$INSTALL_DIR/opendictate-client.py"
chmod +x "$INSTALL_DIR/launch_wizard.py"

ln -sf "$INSTALL_DIR/opendictate-client.py" "$HOME/.local/bin/opendictate"
chmod +x "$HOME/.local/bin/opendictate"

echo "📝 Creando acceso directo de escritorio..."
cat > "$HOME/.local/share/applications/opendictate.desktop" << DESK_EOF
[Desktop Entry]
Type=Application
Name=OpenDictate
Comment=Global voice dictation assistant powered by faster-whisper and Gemini AI
Exec=${HOME}/.local/share/opendictate/.venv/bin/python ${HOME}/.local/share/opendictate/opendictate-daemon.py --force-start
Icon=${HOME}/.local/share/opendictate/img/logo.png
Terminal=false
Categories=Utility;AudioVideo;Accessibility;
Keywords=dictate;whisper;voice;speech;transcribe;
DESK_EOF

echo "🔄 Iniciando demonio OpenDictate..."
pkill -9 -f opendictate-daemon.py || true
rm -f /tmp/opendictate.socket /tmp/opendictate_state.json*
sleep 1

export DISPLAY="${DISPLAY:-:0}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"

# Launch daemon detached in a new process group/session
setsid "$VENV_DIR/bin/python" -u "$INSTALL_DIR/opendictate-daemon.py" --force-start > "$INSTALL_DIR/opendictate.log" 2>&1 &
sleep 2

# Verify daemon is running
if pgrep -f opendictate-daemon.py > /dev/null; then
    echo "✅ Demonio OpenDictate activo y en ejecución."
else
    echo "⚠️ Advertencia: No se pudo verificar el demonio tras el inicio."
fi

if [ -d "$HOME/.config/omarchy" ] && command -v omarchy-restart-shell &> /dev/null; then
    echo "🔄 Reiniciando shell de Omarchy..."
    omarchy-restart-shell || true
fi

echo "✅ Instalación y despliegue completados exitosamente."
echo ""
echo "Comandos disponibles:"
echo "  opendictate --toggle-record-send    (Alternar grabación / envío)"
echo "  opendictate --settings              (Abrir panel de Ajustes)"
echo "  opendictate --wizard                (Abrir Asistente Inicial)"


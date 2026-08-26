#!/bin/bash
set -e

INSTALL_DIR="$HOME/.local/share/opendictate"
VENV_DIR="$INSTALL_DIR/.venv"
OPENDECK_PLUGINS_DIR="$HOME/.config/opendeck/plugins"
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

echo "🧩 Desplegando Extensión de GNOME Shell..."
mkdir -p "$GNOME_EXT_DIR"
cp -r gnome-extension/com.kirulab.opendictate@kirulab.com/* "$GNOME_EXT_DIR/"
if command -v gnome-extensions &> /dev/null; then
    gnome-extensions disable "com.kirulab.opendictate@kirulab.com" 2>/dev/null || true
    sleep 0.5
    gnome-extensions enable "com.kirulab.opendictate@kirulab.com" 2>/dev/null || true
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
    uv pip install faster-whisper google-genai pycairo keyring --python "$VENV_DIR"

    if command -v nvidia-smi &> /dev/null || (command -v lspci &> /dev/null && lspci | grep -iq nvidia); then
        echo "⚡ Tarjeta NVIDIA detectada. Instalando librerías de aceleración CUDA (cuBLAS / cuDNN)..."
        uv pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 --python "$VENV_DIR" || true
    fi
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
rm -f /tmp/opendictate.socket
sleep 1

export DISPLAY="${DISPLAY:-:0}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/1000}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/1000/bus}"
nohup "$VENV_DIR/bin/python" -u "$INSTALL_DIR/opendictate-daemon.py" --force-start > "$INSTALL_DIR/opendictate.log" 2>&1 &
DAEMON_PID=$!
disown $DAEMON_PID
sleep 2

echo "✅ Instalación y despliegue completados exitosamente."
echo ""
echo "Comandos disponibles:"
echo "  opendictate --toggle-record-send    (Alternar grabación / envío)"
echo "  opendictate --settings              (Abrir panel de Ajustes)"
echo "  opendictate --wizard                (Abrir Asistente Inicial)"

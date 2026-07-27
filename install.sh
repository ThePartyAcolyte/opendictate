#!/bin/bash

# Configuration
INSTALL_DIR="$HOME/.local/share/dictate-whisper"
AUTOSTART_DIR="$HOME/.config/autostart"
VENV_DIR="$INSTALL_DIR/.venv"

echo "🚀 Iniciando instalación de OpenDictate..."

echo "📦 Instalando dependencias de sistema (requiere sudo)..."
sudo apt update
sudo apt install -y gir1.2-ayatanaappindicator3-0.1 wl-clipboard ydotool python3-dev python3-cairo libcairo2-dev libgirepository1.0-dev

echo "📁 Creando directorios..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$AUTOSTART_DIR"

echo "📄 Copiando archivos y scripts..."
cp dictate-daemon.py "$INSTALL_DIR/"
cp dictate-client.py "$INSTALL_DIR/"
cp dictate_config_ui.py "$INSTALL_DIR/"
cp i18n.py "$INSTALL_DIR/"
cp -r core "$INSTALL_DIR/"
cp -r ui "$INSTALL_DIR/"
cp -r plugins "$INSTALL_DIR/"
cp -r img "$INSTALL_DIR/"

echo "🧩 Instalando Extensión de GNOME Shell..."
GNOME_EXT_DIR="$HOME/.local/share/gnome-shell/extensions/com.kirulab.dictate@kirulab.com"
mkdir -p "$GNOME_EXT_DIR"
cp -r gnome-extension/com.kirulab.dictate@kirulab.com/* "$GNOME_EXT_DIR/"

chmod +x "$INSTALL_DIR/dictate-daemon.py"
chmod +x "$INSTALL_DIR/dictate-client.py"

echo "🐍 Configurando entorno virtual híbrido con uv..."
if ! command -v uv &> /dev/null; then
    echo "Instalando uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

rm -rf "$VENV_DIR"
uv venv --system-site-packages --python /usr/bin/python3 "$VENV_DIR"
uv pip install faster-whisper google-genai pycairo keyring --python "$VENV_DIR"

echo "🔧 Actualizando shebangs para usar el entorno virtual..."
sed -i "1s|.*|#!$VENV_DIR/bin/python|" "$INSTALL_DIR/dictate-daemon.py"
sed -i "1s|.*|#!$VENV_DIR/bin/python|" "$INSTALL_DIR/dictate-client.py"

echo "⚙️ Configurando acceso directo de aplicación..."
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/dictate-whisper.desktop" << EOF
[Desktop Entry]
Type=Application
Name=OpenDictate
Comment=Background daemon for global voice dictation using faster-whisper
Exec=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/dictate-daemon.py
Hidden=false
NoDisplay=false
Icon=$INSTALL_DIR/img/logo.png
Terminal=false
Categories=Utility;
EOF

echo "✅ Instalación completada."
echo ""
echo "Para iniciar el demonio ahora, ejecuta:"
echo "  nohup $INSTALL_DIR/dictate-daemon.py >/dev/null 2>&1 &"
echo ""
echo "Para usarlo desde un atajo de teclado o OpenDeck:"
echo "  $INSTALL_DIR/dictate-client.py"

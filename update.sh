#!/bin/bash

INSTALL_DIR="$HOME/.local/share/dictate-whisper"

echo "🔄 Actualizando archivos del sistema..."

cp dictate-daemon.py "$INSTALL_DIR/"
cp dictate-client.py "$INSTALL_DIR/"
cp dictate_config_ui.py "$INSTALL_DIR/"
cp i18n.py "$INSTALL_DIR/"
cp -r core "$INSTALL_DIR/"
cp -r ui "$INSTALL_DIR/"
cp -r plugins "$INSTALL_DIR/"

echo "🧩 Actualizando Extensión de GNOME Shell..."
GNOME_EXT_DIR="$HOME/.local/share/gnome-shell/extensions/com.kirulab.dictate@kirulab.com"
mkdir -p "$GNOME_EXT_DIR"
cp -r gnome-extension/com.kirulab.dictate@kirulab.com/* "$GNOME_EXT_DIR/"

echo "📦 Instalando plugin en OpenDeck..."
rm -rf "$HOME/.config/opendeck/plugins/com.butcherwutcher.dictate.sdplugin"
rm -rf "$HOME/.config/opendeck/plugins/com.kirulab.dictate.sdplugin"
cp -r plugins/com.kirulab.dictate.sdplugin "$HOME/.config/opendeck/plugins/"

chmod +x "$INSTALL_DIR/dictate-daemon.py"
chmod +x "$INSTALL_DIR/dictate-client.py"
cp "$INSTALL_DIR/dictate-client.py" "$HOME/.local/bin/dictate"
chmod +x "$HOME/.local/bin/dictate"

echo "📝 Creando acceso directo de aplicación..."
mkdir -p "$HOME/.local/share/applications"
cp -r img "$INSTALL_DIR/"
cat > "$HOME/.local/share/applications/dictate-whisper.desktop" << EOF
[Desktop Entry]
Type=Application
Name=OpenDictate
Comment=Background daemon for global voice dictation
Exec=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/dictate-daemon.py
Icon=$INSTALL_DIR/img/logo.png
Terminal=false
Categories=Utility;
EOF

echo "🔄 Reiniciando demonio..."
pkill -9 -f dictate-daemon.py
sleep 1
if command -v systemd-run &>/dev/null; then
    systemd-run --user --unit=dictate-daemon "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/dictate-daemon.py" --force-start >/dev/null 2>&1
else
    nohup "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/dictate-daemon.py" --force-start >/dev/null 2>&1 &
fi

echo "✅ Actualización completada."

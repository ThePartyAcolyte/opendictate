#!/bin/bash
set -e

# =============================================================================
# OpenDictate Debian (.deb) Package Builder
# =============================================================================

NIGHTLY=false
if [ "$1" = "--nightly" ]; then
    NIGHTLY=true
fi

RAW_VERSION=$(python3 -c 'import sys; sys.path.insert(0, "."); from core.__version__ import __version__; print(__version__)' 2>/dev/null || echo "1.2.0-rc1")
if [ "$NIGHTLY" = "true" ]; then
    BUILD_DATE=$(date +%Y%m%d)
    BASE_VERSION=$(echo "$RAW_VERSION" | sed 's/-.*//')
    VERSION="${BASE_VERSION}-nightly.${BUILD_DATE}"
else
    VERSION="${RAW_VERSION}"
fi

PKG_NAME="opendictate"
ARCH="all"
BUILD_DIR="$(pwd)/build_deb"
PKG_DIR="${BUILD_DIR}/${PKG_NAME}_${VERSION}_${ARCH}"

echo "📦 Construyendo paquete Debian para OpenDictate v${VERSION}..."

# Clean old build
rm -rf "$BUILD_DIR"
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}/opt/opendictate"
mkdir -p "${PKG_DIR}/usr/bin"
mkdir -p "${PKG_DIR}/usr/share/applications"
mkdir -p "${PKG_DIR}/usr/share/gnome-shell/extensions/com.kirulab.opendictate@kirulab.com"
mkdir -p "${PKG_DIR}/usr/share/icons/hicolor/512x512/apps"

# 1. Copiar archivos de la aplicación a /opt/opendictate
echo "📁 Copiando código fuente y módulos a /opt/opendictate..."
cp opendictate-daemon.py "${PKG_DIR}/opt/opendictate/"
cp opendictate-client.py "${PKG_DIR}/opt/opendictate/"
cp opendictate_config_ui.py "${PKG_DIR}/opt/opendictate/"
cp launch_wizard.py "${PKG_DIR}/opt/opendictate/"
cp i18n.py "${PKG_DIR}/opt/opendictate/"
cp -r i18n "${PKG_DIR}/opt/opendictate/"
cp -r core "${PKG_DIR}/opt/opendictate/"
cp -r ui "${PKG_DIR}/opt/opendictate/"
cp -r plugins "${PKG_DIR}/opt/opendictate/"
cp -r img "${PKG_DIR}/opt/opendictate/"

# Sincronizar versión en manifest de OpenDeck y GNOME Extension
if [ -f "${PKG_DIR}/opt/opendictate/plugins/com.kirulab.opendictate.sdplugin/manifest.json" ]; then
    sed -i "s/\"Version\": \".*\"/\"Version\": \"${VERSION}\"/" "${PKG_DIR}/opt/opendictate/plugins/com.kirulab.opendictate.sdplugin/manifest.json"
fi

# 2. Copiar Plugin de Omarchy Shell
echo "🪄 Copiando Plugin de Omarchy Shell a /usr/share/omarchy/shell/plugins..."
mkdir -p "${PKG_DIR}/usr/share/omarchy/shell/plugins/com.kirulab.opendictate"
cp -r plugins/omarchy/opendictate/* "${PKG_DIR}/usr/share/omarchy/shell/plugins/com.kirulab.opendictate/"

# 3. Copiar Extensión de GNOME Shell
echo "🧩 Copiando Extensión de GNOME Shell a /usr/share/gnome-shell/extensions..."
cp -r gnome-extension/com.kirulab.opendictate@kirulab.com/* "${PKG_DIR}/usr/share/gnome-shell/extensions/com.kirulab.opendictate@kirulab.com/"

if [ -f "${PKG_DIR}/usr/share/gnome-shell/extensions/com.kirulab.opendictate@kirulab.com/metadata.json" ]; then
    python3 -c "
import json
p = '${PKG_DIR}/usr/share/gnome-shell/extensions/com.kirulab.opendictate@kirulab.com/metadata.json'
with open(p, 'r') as f:
    d = json.load(f)
d['version-name'] = '${VERSION}'
with open(p, 'w') as f:
    json.dump(d, f, indent=2)
"
fi

# 3. Copiar Íconos y Desktop Entry
echo "🖼️ Configurando acceso directo e íconos..."
if [ -f "img/logo.png" ]; then
    cp img/logo.png "${PKG_DIR}/usr/share/icons/hicolor/512x512/apps/opendictate.png"
fi

cat > "${PKG_DIR}/usr/share/applications/opendictate.desktop" << 'DESK_EOF'
[Desktop Entry]
Type=Application
Name=OpenDictate
Comment=Voice dictation assistant for Linux powered by faster-whisper and Gemini AI
Exec=/usr/bin/opendictate
Icon=opendictate
Terminal=false
Categories=Utility;AudioVideo;Accessibility;
Keywords=dictate;whisper;voice;speech;transcribe;
DESK_EOF

# 4. Crear ejecutable en /usr/bin
cat > "${PKG_DIR}/usr/bin/opendictate" << 'BIN_EOF'
#!/bin/bash
if [ "$1" = "--daemon" ] || [ "$1" = "--start" ]; then
    shift
    if [ -d "/opt/opendictate/.venv" ]; then
        exec /opt/opendictate/.venv/bin/python /opt/opendictate/opendictate-daemon.py "$@"
    else
        exec /usr/bin/python3 /opt/opendictate/opendictate-daemon.py "$@"
    fi
else
    if [ -d "/opt/opendictate/.venv" ]; then
        exec /opt/opendictate/.venv/bin/python /opt/opendictate/opendictate-client.py "$@"
    else
        exec /usr/bin/python3 /opt/opendictate/opendictate-client.py "$@"
    fi
fi
BIN_EOF
chmod +x "${PKG_DIR}/usr/bin/opendictate"

# 5. Crear DEBIAN/control
cat > "${PKG_DIR}/DEBIAN/control" << CTRL_EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, gir1.2-ayatanaappindicator3-0.1, ydotool, wl-clipboard, wmctrl, xdotool, python3-pyatspi, python3-cairo, curl
Maintainer: Tomás D. López <butcherwutcher@outlook.com>
Description: Global local voice dictation for Linux (faster-whisper + AI)
 OpenDictate is a background voice dictation daemon with real-time feedback,
 GNOME Shell extension support, OpenDeck hardware integration, and interactive
 floating controls.
CTRL_EOF

# 6. Crear DEBIAN/postinst
cat > "${PKG_DIR}/DEBIAN/postinst" << 'POST_EOF'
#!/bin/bash
set -e

INSTALL_DIR="/opt/opendictate"
VENV_DIR="${INSTALL_DIR}/.venv"

echo "🐍 Inicializando entorno virtual Python para OpenDictate..."
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh || true
    export PATH="$HOME/.cargo/bin:/root/.cargo/bin:$PATH"
fi

if command -v uv &> /dev/null; then
    uv venv --system-site-packages --python /usr/bin/python3 "$VENV_DIR" || true
    uv pip install faster-whisper google-genai pycairo keyring --python "$VENV_DIR" || true
    if command -v nvidia-smi &> /dev/null || (command -v lspci &> /dev/null && lspci | grep -iq nvidia); then
        echo "⚡ Tarjeta NVIDIA detectada. Instalando librerías de aceleración CUDA..."
        uv pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 --python "$VENV_DIR" || true
    fi
else
    python3 -m venv --system-site-packages "$VENV_DIR" || true
    "$VENV_DIR/bin/pip" install faster-whisper google-genai pycairo keyring || true
    if command -v nvidia-smi &> /dev/null || (command -v lspci &> /dev/null && lspci | grep -iq nvidia); then
        echo "⚡ Tarjeta NVIDIA detectada. Instalando librerías de aceleración CUDA..."
        "$VENV_DIR/bin/pip" install nvidia-cublas-cu12 nvidia-cudnn-cu12 || true
    fi
fi

chmod -R 755 /opt/opendictate
chmod +x /usr/bin/opendictate
rm -f /usr/bin/dictate

if command -v update-desktop-database &> /dev/null; then
    update-desktop-database -q || true
fi

echo "✅ OpenDictate instalado exitosamente."
POST_EOF
chmod 755 "${PKG_DIR}/DEBIAN/postinst"

# 7. Crear DEBIAN/postrm
cat > "${PKG_DIR}/DEBIAN/postrm" << 'RM_EOF'
#!/bin/bash
set -e

if [ "$1" = "purge" ] || [ "$1" = "remove" ]; then
    rm -rf /opt/opendictate
    rm -f /usr/bin/opendictate
fi

if command -v update-desktop-database &> /dev/null; then
    update-desktop-database -q || true
fi
RM_EOF
chmod 755 "${PKG_DIR}/DEBIAN/postrm"

# 8. Empaquetar con dpkg-deb o ar/tar
DEB_FILE="${BUILD_DIR}/${PKG_NAME}_${VERSION}_${ARCH}.deb"
if command -v dpkg-deb &> /dev/null; then
    echo "🔨 Generando paquete .deb con dpkg-deb..."
    dpkg-deb --build --root-owner-group "$PKG_DIR" "$DEB_FILE"
else
    echo "🔨 Generando paquete .deb con ar y tar (fallback sin dpkg-deb)..."
    echo "2.0" > "${BUILD_DIR}/debian-binary"
    (cd "${PKG_DIR}/DEBIAN" && tar --owner=0 --group=0 --numeric-owner -czf "${BUILD_DIR}/control.tar.gz" ./*)
    (cd "${PKG_DIR}" && tar --owner=0 --group=0 --numeric-owner --exclude="DEBIAN" -czf "${BUILD_DIR}/data.tar.gz" ./*)
    (cd "${BUILD_DIR}" && ar rcs "${DEB_FILE}" debian-binary control.tar.gz data.tar.gz)
    rm -f "${BUILD_DIR}/debian-binary" "${BUILD_DIR}/control.tar.gz" "${BUILD_DIR}/data.tar.gz"
fi

echo "🎉 Paquete creado exitosamente: ${DEB_FILE}"
echo ""
echo "Para instalarlo en cualquier sistema Ubuntu/Debian ejecuta:"
echo "  sudo dpkg -i ${DEB_FILE} || sudo apt-get install -f -y"

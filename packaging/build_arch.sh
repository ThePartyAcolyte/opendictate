#!/bin/bash
set -e

# =============================================================================
# OpenDictate Arch Linux (.pkg.tar.zst) Package & PKGBUILD Builder
# =============================================================================

NIGHTLY=false
if [ "$1" = "--nightly" ]; then
    NIGHTLY=true
fi

RAW_VERSION=$(python3 -c 'import sys; sys.path.insert(0, "."); from core.__version__ import __version__; print(__version__)' 2>/dev/null || echo "1.2.0")
if [ "$NIGHTLY" = "true" ]; then
    BUILD_DATE=$(date +%Y%m%d)
    BASE_VERSION=$(echo "$RAW_VERSION" | sed 's/-.*//' | tr '-' '.')
    VERSION="${BASE_VERSION}.nightly.${BUILD_DATE}"
    PKGVER="${VERSION}"
else
    PKGVER=$(echo "$RAW_VERSION" | tr '-' '.')
fi

PKG_NAME="opendictate"
PKGREL="1"
ARCH="any"
BUILD_DIR="$(pwd)/build_arch"
PKG_DIR="${BUILD_DIR}/pkg/${PKG_NAME}"

echo "📦 Construyendo paquete Arch Linux (.pkg.tar.zst) para OpenDictate v${PKGVER}-${PKGREL}..."

# Clean old build
rm -rf "$BUILD_DIR"
mkdir -p "${PKG_DIR}/opt/opendictate"
mkdir -p "${PKG_DIR}/usr/bin"
mkdir -p "${PKG_DIR}/usr/share/applications"
mkdir -p "${PKG_DIR}/usr/share/icons/hicolor/512x512/apps"
mkdir -p "${PKG_DIR}/usr/share/omarchy/shell/plugins/com.kirulab.opendictate"
mkdir -p "${PKG_DIR}/usr/share/gnome-shell/extensions/com.kirulab.opendictate@kirulab.com"

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

# Sincronizar versión en plugins
if [ -f "${PKG_DIR}/opt/opendictate/plugins/com.kirulab.opendictate.sdplugin/manifest.json" ]; then
    sed -i "s/\"Version\": \".*\"/\"Version\": \"${PKGVER}\"/" "${PKG_DIR}/opt/opendictate/plugins/com.kirulab.opendictate.sdplugin/manifest.json"
fi

# 2. Copiar Plugin de Omarchy Shell
echo "🪄 Copiando Plugin de Omarchy Shell a /usr/share/omarchy/shell/plugins..."
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
d['version-name'] = '${PKGVER}'
with open(p, 'w') as f:
    json.dump(d, f, indent=2)
"
fi

# 4. Copiar Íconos y Desktop Entry
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

# 5. Crear ejecutable wrapper en /usr/bin
cat > "${PKG_DIR}/usr/bin/opendictate" << 'BIN_EOF'
#!/bin/bash
if [ "$1" = "--daemon" ] || [ "$1" = "--start" ]; then
    shift
    if [ -d "$HOME/.local/share/opendictate/.venv" ]; then
        exec "$HOME/.local/share/opendictate/.venv/bin/python" /opt/opendictate/opendictate-daemon.py "$@"
    elif [ -d "/opt/opendictate/.venv" ]; then
        exec /opt/opendictate/.venv/bin/python /opt/opendictate/opendictate-daemon.py "$@"
    else
        exec /usr/bin/python3 /opt/opendictate/opendictate-daemon.py "$@"
    fi
else
    if [ -d "$HOME/.local/share/opendictate/.venv" ]; then
        exec "$HOME/.local/share/opendictate/.venv/bin/python" /opt/opendictate/opendictate-client.py "$@"
    elif [ -d "/opt/opendictate/.venv" ]; then
        exec /opt/opendictate/.venv/bin/python /opt/opendictate/opendictate-client.py "$@"
    else
        exec /usr/bin/python3 /opt/opendictate/opendictate-client.py "$@"
    fi
fi
BIN_EOF
chmod +x "${PKG_DIR}/usr/bin/opendictate"

# 6. Crear .INSTALL script para pacman
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

post_upgrade() {
    post_install
}

post_remove() {
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database -q || true
    fi
}
INSTALL_EOF

# 7. Generar .PKGINFO para pacman
INSTALLED_SIZE=$(du -sb "${PKG_DIR}" | cut -f1)
cat > "${PKG_DIR}/.PKGINFO" << PKGINFO_EOF
pkgname = ${PKG_NAME}
pkgver = ${PKGVER}-${PKGREL}
pkgdesc = Global voice dictation for Linux (faster-whisper + Gemini AI) with native Omarchy and GNOME integration
url = https://github.com/ThePartyAcolyte/opendictate
builddate = $(date +%s)
packager = Tomás D. López <butcherwutcher@outlook.com>
size = ${INSTALLED_SIZE}
arch = ${ARCH}
license = MIT
depend = python>=3.10
depend = python-gobject
depend = gtk3
depend = libayatana-appindicator
depend = ydotool
depend = wl-clipboard
depend = grim
depend = curl
optdepend = ctranslate2: GPU accelerated transcription
optdepend = cuda: NVIDIA acceleration
optdepend = cudnn: Deep learning NVIDIA acceleration
PKGINFO_EOF

# 8. Empaquetar en .pkg.tar.zst directamente
echo "🔨 Comprimiendo paquete Arch Linux con zstd..."
ARCH_PKG="${BUILD_DIR}/${PKG_NAME}-${PKGVER}-${PKGREL}-${ARCH}.pkg.tar.zst"
(
    cd "${PKG_DIR}"
    # Create package archive
    tar --zstd -cf "${ARCH_PKG}" .PKGINFO *
)

echo "🎉 Paquete Arch Linux creado exitosamente: ${ARCH_PKG}"
echo ""
echo "Para instalarlo en cualquier sistema Arch/Manjaro/Omarchy ejecuta:"
echo "  sudo pacman -U ${ARCH_PKG}"

#!/bin/bash
set -e

echo "🗑️ Desinstalando OpenDictate (purge completo)..."

echo "🛑 Deteniendo procesos en ejecución..."
pkill -9 -f "opendictate-daemon.py" 2>/dev/null || true
pkill -9 -f "dictate-daemon.py" 2>/dev/null || true
pkill -9 -f "com.kirulab.opendictate.sdplugin" 2>/dev/null || true
pkill -9 -f "com.kirulab.dictate.sdplugin" 2>/dev/null || true
pkill -9 -f "com.butcherwutcher.dictate.sdplugin" 2>/dev/null || true
sleep 1

echo "📁 Eliminando instalaciones..."
# Instalación actual (opendictate)
rm -rf "$HOME/.local/share/opendictate"
# Instalación anterior (dictate-whisper)
rm -rf "$HOME/.local/share/dictate-whisper"

echo "📁 Eliminando configuración..."
rm -rf "$HOME/.config/opendictate"
rm -rf "$HOME/.config/dictate-whisper"

echo "🔨 Eliminando binarios y accesos directos..."
rm -f "$HOME/.local/bin/opendictate"
rm -f "$HOME/.local/bin/dictate"
rm -f "$HOME/.local/share/applications/opendictate.desktop"
rm -f "$HOME/.local/share/applications/dictate-whisper.desktop"
rm -f "$HOME/.local/share/applications/dictate.desktop"

echo "⏱️ Eliminando autostart..."
rm -f "$HOME/.config/autostart/opendictate.desktop"
rm -f "$HOME/.config/autostart/dictate-daemon.desktop"
rm -f "$HOME/.config/autostart/dictate.desktop"

echo "🧩 Desinstalando extensión GNOME Shell..."
gnome-extensions disable com.kirulab.opendictate@kirulab.com 2>/dev/null || true
rm -rf "$HOME/.local/share/gnome-shell/extensions/com.kirulab.opendictate@kirulab.com"

echo "📦 Eliminando plugins de OpenDeck..."
rm -rf "$HOME/.config/opendeck/plugins/com.kirulab.opendictate.sdplugin"
rm -rf "$HOME/.config/opendeck/plugins/com.kirulab.dictate.sdplugin"
rm -rf "$HOME/.config/opendeck/plugins/com.butcherwutcher.dictate.sdplugin"

echo "🧹 Limpiando archivos temporales..."
rm -f /tmp/opendictate.socket
rm -f /tmp/opendictate_state.json
rm -f /tmp/dictate_daemon.socket
rm -f /tmp/dictate_state.json
rm -f /tmp/opendictate_plugin.log
rm -f /tmp/dictate_recording.wav.pcm
rm -f /tmp/dictate_vision.png

echo "🔑 Eliminando credenciales del keyring..."
secret-tool clear service OpenDictate 2>/dev/null || true

echo "✅ OpenDictate ha sido desinstalado completamente del sistema."

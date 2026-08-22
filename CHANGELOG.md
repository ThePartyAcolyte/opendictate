# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-20

### Added
- **Global Binary Rename**: Application officially rebranded from `dictate` to `opendictate`.
- **Per-App AI Profiles**: A dedicated UI in Settings to configure unique System Prompts depending on the active window (e.g., Markdown for Obsidian, Bash for Terminal).
- **Dynamic Tray Fallback**: Intelligent backend selection (`AppIndicator` for Wayland, `Gtk.StatusIcon` for X11) to ensure flawless rendering and preserve left-click actions where supported.
- **GNOME Extension Updates**: Full compatibility with GNOME 45-51, dynamically tracking the daemon's Unix socket (`/tmp/opendictate.socket`).
- **Debian Packaging**: Standalone builder script (`packaging/build_deb.sh`) to bundle dependencies and automate system-wide installations.

### Changed
- **UI Refactor**: Extracted the Application Profiles manager into a modal Dialog (`AppProfilesDialog`) to declutter the main Settings sidebar.
- **Unified Installer**: `install.sh` and `uninstall.sh` now cleanly manage both legacy (`dictate-whisper`) and modern (`opendictate`) artifacts, extensions, and plugins.
- **OpenDeck UUIDs**: Migrated all Property Inspector and Plugin UUIDs to `com.kirulab.opendictate.sdplugin`.

### Fixed
- Fixed critical syntax parser bug (`invalid decimal literal`) caused by `sed` corrupting string delimiters during installation.
- Fixed silent `ModuleNotFoundError` when triggering global keyboard shortcuts via copied binaries (now properly symlinked).
- Fixed `shutil` missing import crash when attempting to delete downloaded Whisper models.
- Fixed GNOME Extension detection logic parsing localized string outputs from `gnome-extensions show` (now reads `ACTIVE` / `Activado: Sí`).
- Fixed system tray indicator mode persistence (properly sending disable commands to the old GNOME Extension UUID).

### Deprecated
- Dropped `--toggle-autopause` and `--toggle-bubble` from the legacy CLI (integrated directly into the persistent config engine).

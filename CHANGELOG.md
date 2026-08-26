# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-08-25

### Added
- **Adaptive VAD Dynamic Chunking**: Replaced rigid time-based segmentation with content-aware Voice Activity Detection (`core/vad.py`). Segments audio cleanly during conversational pauses (0.6s default).
- **Dynamic Noise Floor Estimation**: Automatic acoustic baseline tracking ($N_{\text{floor}}$) adapting detection sensitivity across different microphones and ambient noise environments.
- **Retroactive Boundary Search & Energy-Valley Fallback**: Proactively searches backward for pauses within a tolerance window (0.4s) when approaching maximum duration (30.0s), or slices at minimum RMS energy valleys to prevent lexical truncation.
- **Whisper 30-Second Mel Spectrogram Alignment**: Default maximum chunk duration set to 30.0 seconds to fully utilize Whisper's receptive field.
- **Modular Internationalization (`i18n/`)**: Complete refactor into modular language packs with 100% string coverage for German (`de`) and French (`fr`), alongside English (`en`) and Spanish (`es`).
- **Interactive VAD Settings UI**: Settings panel controls for silence threshold, maximum chunk duration, fallback tolerance, and minimum chunk length with live persistence.
- **Database Migration v1 -> v2**: Automated SQLite migration routine cleaning up deprecated chunking settings while safely preserving user preferences.

### Changed
- **Text Stitching & Merging**: Eliminated fuzzy heuristic overlap matching in favor of deterministic pause-boundary text concatenation guided by `initial_prompt`.

### Fixed
- **Streaming/Completion Race Condition**: Resolved thread synchronization race condition on completion (`self.transcribe_lock`), eliminating duplicate text appending and trailing hallucinations.

### Known Technical Debt
- **GNOME Shell Extension Popup Menu Localization**: Context menu strings in GNOME Shell extension currently default to English/Spanish pending Gettext / GSettings integration.

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

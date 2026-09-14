# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.1] - 2026-09-14

### Fixed & Refactored (Comprehensive Audit & Hardening)
- **Critical Crash Fixes**: Resolved `NameError` in `core/config.py` by adding `import time`, fixed `ImportError` in `ui/wizard_tui.py`, fixed `AttributeError` in daemon shutdown, and repaired GTK Wizard empty-step navigation.
- **Performance & Security**: Optimized `export_state()` JSON serialization by caching window/shell listings, moved IPC socket to `$XDG_RUNTIME_DIR/opendictate.socket`, robustly handled IPC buffer EOF, and eliminated temporary screenshot files after upload.
- **Packaging & Uninstallation**: Updated `install.sh` and `uninstall.sh` to properly manage OpenDeck plugins (`~/.config/opendeck/plugins/`), handle Omarchy shell integration, and configure Python virtual environments.
- **Dead Code Cleanup**: Deleted legacy patch scripts, unhooked dead voice command wizard UI methods, removed duplicate transcriber loops, and cleaned unused imports across `core/` and `ui/`.
- **UI Deduplication & Centralization**: Refactored `AppProfilesDialog` to use `ConfigManager` APIs, centralized Omarchy color palette extraction, and unified autostart `.desktop` generation.
- **Logging & Exception Hardening**: Replaced silent `except:` blocks with structured `logging.debug()` calls and configured 2 MB `RotatingFileHandler` for OpenDeck plugin logs.
- **i18n & Model Centralization**: Centralized `WHISPER_MODELS_LIST` and `GEMINI_MODELS_LIST` in `core/config.py` and internationalized Gemini Live / AEC calibration status messages across 4 languages.
- **Tests & Documentation**: Added regression unit tests for Keyring retry logic, refactored D-Bus integration tests to use `unittest` mocks, updated IPC specification documentation, and added `TextEncoder` compatibility to GNOME Shell extension.
- **Smart Fallback Backend Downgrade**: Fixed speculative dual-race fallback to only permanently downgrade `stt_backend` to `local_whisper` on hard, unrecoverable API errors (`QUOTA_EXCEEDED`, `INVALID_API_KEY`). Transient failures (`NETWORK_ERROR`, `SERVICE_UNAVAILABLE`) now fall back to local for the current session only, automatically retrying Gemini Live on the next dictation.
- **Omarchy Quick Menu Cleanup**: Removed the Real-Time Streaming toggle from the Omarchy bar widget's quick-access panel. This advanced setting is now exclusively accessible through the full Settings dialog, reducing clutter in everyday use.

## [1.2.0] - 2026-09-13

### Added
- **Speculative Dual Execution & Adaptive Fallback**: Competitive race architecture ensuring zero audio loss. When cloud connectivity drops or latency spikes, OpenDictate transcribes the full audio buffer locally with Faster-Whisper while retrying in parallel via Google Gemini Cloud.
- **Transparent API Error Diagnostics**: Intelligent classification of API failures (`QUOTA_EXCEEDED`, `INVALID_API_KEY`, `SERVICE_UNAVAILABLE`, `NETWORK_ERROR`) with contextual desktop alerts.
- **Gemini Live STT (`gemini-3.5-transcribe-live`)**: Continuous bidirectional real-time audio streaming with sub-200ms latency, zero local compute overhead, and SMART/VERBATIM formatting modes.
- **Dynamic Faster-Whisper Memory Offloading**: Automatically unloads local Whisper models when switching to Gemini Live, dropping daemon RAM usage from ~1.8 GB to <100 MB.
- **Native Omarchy Shell Desktop Notifications**: Full integration with `omarchy-notification-send`, bypassing Do-Not-Disturb (DND) mode for immediate user feedback on dictation actions.
- **Adaptive Corner Radius Syncing**: Settings modal and dialogs dynamically adapt their corner radius (`Style.cornerRadius`) to match Hyprland's `decoration:rounding` configuration.
- **Minimalist Offline Bar Popup**: When the background daemon is inactive, right-clicking the top bar widget presents a clean, single-action Start button.
- **Complete 4-Language Localization (`i18n/`)**: 100% string coverage across all settings, toasts, CLI descriptors, and dialogs for Spanish (`es`), English (`en`), German (`de`), and French (`fr`).
- **Headless D-Bus Session API (`org.kirulab.OpenDictate`)**: Headless recording API with `ReserveCaptureSession`, client UUIDs, multi-app eviction, and custom bar accent colors.
- **Herder Workspace Integration**: Tab-specific focus recovery for agent terminal panes (`omarchy: wang-kapawu`).

### Fixed
- **Daemon Clean Termination & Restartability**: Fixed the Quit action in Omarchy bar widget to cleanly terminate the background daemon, update telemetry state to `OFFLINE`, and allow instant restart.
- **Voice Commands Safety Lock**: Added in-development banner and disabled acoustic triggers by default to prevent stability issues.

## [1.2.0-nightly.20260902] - 2026-09-02
- Multi-distro packaging improvements (.pkg.tar.zst and .deb).
- D-Bus session reservations and multi-app eviction protocols.

## [1.2.0-nightly.20260831] - 2026-08-31
- Initial Gemini Live WebSocket streaming engine implementation.
- Dynamic Faster-Whisper memory unloading.

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

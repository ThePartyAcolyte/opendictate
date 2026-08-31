# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0-nightly.20260831] - 2026-08-31

### Architectural Note: Gemini API Strategy
- **Gemini Live Speech-to-Text (`gemini-3.5-transcribe-live`)**: Added to provide continuous bidirectional real-time audio transcription over WebSockets. Offloads heavy neural compute from the host system, eliminating local GPU/CPU load and reducing daemon RAM consumption from ~1.8 GB to <70 MB.
- **Gemini Flash & Flash-Lite for AI Cleanup (`gemini-3.1-flash-live-preview`)**: Selected as the primary LLM engine for post-transcription cleaning due to its ultra-low time-to-first-token latency (<200ms), high throughput, and generous free-tier API quotas. Delivers fast, intelligent text formatting without requiring local LLM execution.

### Added
- **Gemini Live 3.5 Streaming STT (`core/gemini_live_engine.py`)**: Full bidirectional WebSocket streaming transcription engine with native support for `SMART` (intelligent punctuation/formatting) and `VERBATIM` (exact acoustic fidelity) modes via `google-genai>=2.20.0`.
- **Dynamic Faster-Whisper Memory Offloading (`WhisperEngine.unload_model`)**: Automatically unloads local Faster-Whisper models from RAM when switching to Gemini Live, freeing 1.5 GB to 3.5 GB of memory while allowing on-demand fallback if cloud services are unavailable.
- **Configurable LLM Thinking Budget (`llm_thinking_level`)**: Settings control enabling granular adjustment of thinking reasoning depth (`minimal`, `low`, `medium`, `high`) for Gemini 2.5/3.0 models during AI cleanup.
- **Subtle Visual Feedback Palette**: Distinct, non-intrusive color cues across the UI:
  - **GNOME Shell Indicator**: Standby microphone icon illuminates in Gemini Diamond Blue (`#5c8df6`) and recording turns purple (`#7c5ce7`) when Live STT is active.
  - **Floating OSD Bubble**: Waveform energy bars rendered in Gemini blue/indigo (`rgba(92, 141, 246, 0.85)`), and recording toggle styled in translucent purple.
- **Hardened GNOME Keyring Credential Persistence (`core/config.py`)**: Protected API keys from accidental deletion during generic configuration saves and implemented exponential-backoff retries with in-memory caching (`_get_api_key_safe`) to eliminate cold-boot D-Bus race conditions.
- **Modular Devlog Architecture (`devlog/`)**: Established structured per-session engineering log files to track architectural decisions, benchmarks, and ongoing development history.

### Experimental (WIP / Inactive by default)
- **Acoustic Echo Cancellation & Playback Subtraction (`core/aec.py`, `core/audio_concurrency.py`)**: Normalized Least Mean Squares (NLMS) adaptive filter tapping PipeWire monitor sinks to subtract background music and desktop video audio from the microphone stream prior to VAD and speech processing (`aec_enabled: false`).
- **Background Voice Command Engine (`core/voice_commands.py`, `ui/sample_recorder.py`)**: Continuous idle-state voice trigger recognizer with multi-phrase template distance matching and interactive custom sample recorder UI (`voice_commands_enabled: false`).

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

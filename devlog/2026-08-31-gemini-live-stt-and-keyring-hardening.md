# Devlog: Gemini Live STT 3.5 Integration, LLM Cleanup Optimization, and Keyring Hardening

**Date:** 2026-08-31  
**Author:** OpenDictate Engineering  
**Scope:** `core/gemini_live_engine.py`, `core/config.py`, `core/engine.py`, `opendictate-daemon.py`, `ui/bubble.py`, `gnome-extension/`

---

## 1. Context and Architectural Rationale

### Why New Gemini APIs Were Added:
1. **Gemini Live Speech-to-Text (`gemini-3.5-transcribe-live`)**:
   - **Zero Local Footprint & Memory Efficiency**: Running local Faster-Whisper models (especially `medium` or `large-v3`) requires 1.5 GB to 3.5 GB of resident RAM and sustained CPU/GPU compute during inference. Offloading STT to `gemini-3.5-transcribe-live` reduces the background daemon's memory footprint to under 70 MB.
   - **Real-Time Bidirectional WebSockets**: Audio is streamed in 16 kHz 16-bit PCM chunks as the user speaks. The server returns speculative interim hypotheses (`interim_input_transcription`) for live visual preview and authoritative segments (`input_transcription`) with automatic punctuation (`SMART` mode) or verbatim acoustic fidelity (`VERBATIM` mode).
2. **Gemini Flash / Flash-Lite for Post-Processing AI Cleanup (`gemini-3.1-flash-live-preview`)**:
   - **Ultra-Low Latency & High Quotas**: The Flash / Flash-Lite tier provides near-instantaneous streaming generation (<200 ms TTFT) with generous free rate limits, making it ideal for real-time punctuation correction, grammar cleanup, and domain-specific vocabulary fixing without burdening local host hardware.
   - **Thinking Budget Control**: Configurable thinking budget levels (`minimal`, `low`, `medium`, `high`) allow users to balance latency against reasoning depth for complex dictations.

---

## 2. Key Engineering Challenges and Resolutions

### A. WebSocket Finalization Latency in `stop_session()`
- **Issue**: When the user pressed `Send`, `stop_session()` called `self._thread.join(timeout=3.0)`. Because the `session.receive()` async iterator holds an open bidirectional stream waiting for more audio, the thread never exited spontaneously, resulting in a mandatory 3.0-second delay before returning the final transcript.
- **Resolution**: Implemented a thread-safe `threading.Event` (`self._final_event`). When stream termination is signaled (`audio_stream_end=True`), the receiver loop unblocks and sets `_final_event` immediately upon receiving the final `input_transcription` or `turn_complete` frame. Final text is returned within ~50–100 ms.

### B. Dynamic Faster-Whisper Model Unloading
- **Issue**: Even when configured for `stt_backend == "gemini_live"`, the daemon loaded Faster-Whisper unconditionally on boot, consuming 83% system RAM.
- **Resolution**:
  - Added `unload_model()` to `WhisperEngine` (`core/engine.py`) to release the model reference and trigger `gc.collect()`.
  - In `opendictate-daemon.py`, model loading is bypassed at startup if `stt_backend == "gemini_live"` and an API key is present.
  - If a cloud connection fails or the user switches back to local STT, Whisper is loaded on-demand.

### C. GNOME Keyring vs. SQLite Credential Security
- **Issue**: The API key was previously getting cleared after settings modifications. When `load_config()` experienced a cold-boot D-Bus race condition, `cfg["api_key"]` evaluated to `""`. A subsequent `save_config()` call for unrelated settings triggered `keyring.delete_password()`, permanently destroying the stored key.
- **Resolution**:
  - Maintained GNOME Keyring / SecretService as the single authoritative storage mechanism for credentials to preserve OS-level encryption at rest (PAM/login-secured).
  - Implemented `_get_api_key_safe()` with exponential retry and process-level memory caching (`_cached_api_key`).
  - Restricted `keyring.delete_password()` strictly to explicit deletions initiated from the settings UI (`explicit_api_key_update=True`).

### D. Subtle Non-Intrusive Visual Telemetry
- **Design Decision**: Rejected intrusive textual badges and emojis in favor of a clean, subtle palette shift:
  - **GNOME Shell Indicator**: Microphone icon tinted in Gemini Diamond Blue (`#5c8df6`) in standby/IDLE and recording purple (`#7c5ce7`) during Live mode.
  - **Floating OSD Bubble**: Waveform audio energy bars rendered in Gemini Indigo/Blue (`rgba(92, 141, 246, 0.85)`), and recording toggle styled with translucent purple accent (`rgba(108, 92, 231, 0.40)`).

---

## 3. Verification & Test Results
- Automated unit test suite executed: **40 tests passed** (`OK`).
- Deployment executed via `./install.sh` updating local user binaries and GNOME Shell extension.
- Production logs (`daemon.log`) verified clean WebSocket handshakes, sub-100ms session stops, and zero RAM waste.

# Devlog: Acoustic Echo Cancellation (AEC) & Idle Voice Commands Engine (Experimental WIP)

**Date:** 2026-08-28  
**Author:** OpenDictate Engineering  
**Scope:** `core/aec.py`, `core/audio_concurrency.py`, `core/voice_commands.py`, `ui/sample_recorder.py`

---

## 1. Context & Motivation

When operating a voice dictation assistant on desktop environments:
1. **Background Audio Interference**: Users frequently listen to music, podcasts, or video streams while working. Traditional VAD models and Whisper can hallucinate or fail to distinguish spoken dictation from desktop speaker playback picked up by the microphone.
2. **Hands-Free Activation**: Pressing global hotkeys or clicking UI elements interrupts workflow. An idle wake-word / voice command recognizer allows users to trigger recording, send text, or execute actions entirely hands-free.

---

## 2. Architectural Design & Implementation

### A. Acoustic Echo Cancellation & Playback Subtraction (`core/aec.py`, `core/audio_concurrency.py`)
- **Mechanism**:
  - Leverages PipeWire / PulseAudio monitor sinks (`core/audio_concurrency.py`) to tap the raw desktop audio stream in parallel with the microphone input stream.
  - Implements an adaptive Normalized Least Mean Squares (NLMS) filter with dynamic spectral subtraction (`core/aec.py`).
  - Correlates the reference speaker playback signal with the microphone capture, estimating the acoustic impulse response and subtracting the speaker bleed prior to passing audio to the VAD and STT engines.
- **Current Status**:
  - Core filter algorithms and concurrency audio streams implemented.
  - Marked as **Experimental / Inactive by default** (`aec_enabled: false`) pending real-world latency calibration across diverse sound hardware and room reverberation profiles.

### B. Idle Voice Command Engine (`core/voice_commands.py`, `ui/sample_recorder.py`)
- **Mechanism**:
  - Operates a lightweight continuous ring buffer in the background during `IDLE` state.
  - Matches incoming speech segments against pre-recorded or user-calibrated voice command templates using dynamic time warping and acoustic feature distance scoring.
  - Includes a dedicated GUI recorder (`ui/sample_recorder.py`) to let users record custom activation samples for trigger phrases (e.g., *"Dictar"*, *"Enviar"*, *"Cancelar"*).
- **Current Status**:
  - Template matching engine and sample recorder UI built.
  - Marked as **Experimental / Inactive by default** (`voice_commands_enabled: false`) pending optimization against false-positive wakeups from ambient conversation and high-noise environments.

---

## 3. Outstanding Technical Debt & Future Milestones
- [ ] Implement adaptive delay estimation in `core/aec.py` to synchronize PipeWire monitor sink buffer latency with physical microphone hardware latency.
- [ ] Integrate a compact, low-resource ONNX wake-word neural classifier to complement acoustic template matching in `core/voice_commands.py`.
- [ ] Expose advanced calibration sliders in the Settings panel under an *Experimental Features* tab.

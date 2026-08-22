<div align="center">
  <img src="img/logo.png" width="150" alt="OpenDictate Logo" />
  <h1>OpenDictate</h1>
  <p><strong>Privacy-First, Global Voice Dictation for Linux</strong></p>
</div>

<hr>

OpenDictate is an omnipresent, background voice dictation daemon for Linux desktop environments. Built with a strict privacy-first philosophy, it leverages local on-device transcription to act as a system-wide microphone layer. It allows you to dictate text directly into any focused window—exactly like native dictation on macOS or Windows—without sending your voice audio to third-party servers.

## 🛡️ Core Philosophy: Privacy & Local Processing

The primary objective of OpenDictate is to guarantee that your voice data never leaves your machine. 
All audio capture, Voice Activity Detection (VAD), and speech-to-text inference are handled 100% locally using **`faster-whisper`** (CTranslate2). 

*While OpenDictate offers an optional Cloud AI rewriting feature to fix grammar, the core transcription engine is entirely local, private, and independent of any internet connection.*

## 🚀 Key Features

* **100% Local Voice Recognition**: Powered by localized Whisper models.
* **Real-Time Chunk Engine**: Optimized audio chunk processing utilizing PyAudio and WebRTC VAD for low-latency streaming transcription and real-time visual feedback via an OSD (On-Screen Display) floating bubble.
* **Universal DE Compatibility (X11 & Wayland)**:
  * **GNOME (45–51)**: Native top panel extension for seamless Shell integration.
  * **Other DEs (XFCE, Cinnamon, KDE)**: Dynamic system tray fallback utilizing `Gtk.StatusIcon` (XEmbed) for X11 environments to preserve native left-click record actions, and `AyatanaAppIndicator3` (StatusNotifierItem) for pure Wayland environments to prevent coordinate rendering bugs.
* **Smart Window Focus Restoration**: Remembers the target X11/Wayland window (via `xdotool` / `ydotool`) where dictation initiated, restoring focus before pasting to prevent cross-app paste errors during multitasking.
* **Smart Media Control**: Automatically hooks into MPRIS via DBus to pause your media players (Spotify, VLC, YouTube) when you speak, and resumes playback upon completion.
* **Cloud-Independent Deck Integration (OpenDeck)**: Native plugin for OpenDeck (Stream Deck alternative). Control dictation via physical buttons and rotary encoders, featuring real-time visual feedback directly on the hardware keys.

## 🧠 Optional Feature: AI Rewriting & App Profiles

As an extra quality-of-life feature, OpenDictate allows piping the transcribed text through an LLM to fix homophones, grammar, and format the text based on context.

* **Per-App AI Profiles**: Define specific System Prompts depending on the active window. You can instruct the AI to format output as Markdown when focused on Obsidian, or output pure Bash commands when focused on GNOME Terminal.
* **Current Backend**: Google Gemini / Gemma API (Requires API Key). 

---

## 🏗️ Architecture & Technical Stack

OpenDictate is built on a decoupled Daemon-Client architecture communicating via a Unix Domain Socket (`/tmp/opendictate.socket`).

* **Daemon (`opendictate-daemon.py`)**: Runs continuously in the background managing audio streams, loading the Whisper model into VRAM/RAM, and maintaining the GNOME extension state.
* **Client (`opendictate-client.py`)**: A lightweight CLI trigger used to send IPC commands to the daemon.
* **Core Libraries**:
  * `faster-whisper`: Core inference engine.
  * `PyGObject` (`gi.repository.Gtk`): UI settings, dialogs, and Tray management.
  * `pycairo`: For rendering the transparent floating OSD feedback bubble.
  * `pydbus`: MPRIS media control.
  * `xdotool` / `ydotool` / `wl-clipboard`: Window management and clipboard injection.

---

## 📦 Installation (Version 1.0)

### System-wide Debian Package (`.deb`)
1. Download the `.deb` from the Releases page.
2. Install it using `dpkg`:
   ```bash
   sudo dpkg -i opendictate_1.0.0_all.deb || sudo apt-get install -f -y
   ```
*(The package utilizes a `postinst` script to securely build a self-contained Python virtual environment in `/opt/opendictate/.venv`, preventing conflicts with system Python packages).*

### Local User Installation
Installs only for your current user in `~/.local/`.
```bash
git clone https://github.com/ThePartyAcolyte/opendictate.git
cd opendictate
./install.sh
```

---

## ⌨️ CLI / Global Shortcuts

Bind these to your DE's custom keyboard shortcuts.

| Command | Action |
|---------|-------------|
| `opendictate --toggle-record-send` | Push once to start recording. Push again to stop, apply optional cleaning, and inject text. |
| `opendictate --record` | Starts recording (or resumes if paused). |
| `opendictate --pause` | Pauses the current recording without sending. |
| `opendictate --cancel` | Cancels the recording and discards the buffer. |
| `opendictate --send` | Injects the current text and simulates an 'Enter' keypress. |
| `opendictate --settings` | Opens the GTK Configuration UI. |

---

## 🛣️ Roadmap & Technical Debt

- **Native Extensibility for non-GNOME DEs**: Replace the limited System Tray fallback by developing native panel widgets for other Desktop Environments (e.g., QML Plasmoids for KDE Plasma, CJS Applets for Cinnamon) to communicate natively with the Unix socket.
- **Local LLM Backend**: Implement an offline backend (via Ollama or Llama.cpp) for the AI rewriting pipeline, allowing the optional grammar formatting feature to run 100% locally and maintain the absolute privacy philosophy.

---

## ⚖️ License and Credits

* **License**: Released under the MIT License. Copyright (c) 2026 Kirulab / Tomás D. López.
* Engine relies on `faster-whisper` (MIT).

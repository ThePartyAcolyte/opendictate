import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';

const STATE_FILE = '/tmp/dictate_state.json';
const SOCKET_PATH = '/tmp/dictate_daemon.socket';

const Waveform = GObject.registerClass(
class Waveform extends St.DrawingArea {
    _init() {
        super._init({ style_class: 'opendictate-waveform' });
        this._levels = new Array(30).fill(0);
        this._isIndeterminate = false;
        this._pulsePos = 0;
        this._pulseDir = 1;
    }

    setIndeterminate(enable) {
        if (this._isIndeterminate !== enable) {
            this._isIndeterminate = enable;
            this._pulsePos = 0;
            this._pulseDir = 1;
            this.queue_repaint();
        }
    }

    updatePulse() {
        if (!this._isIndeterminate) return;
        this._pulsePos += 0.05 * this._pulseDir;
        if (this._pulsePos >= 1.0) {
            this._pulsePos = 1.0;
            this._pulseDir = -1;
        } else if (this._pulsePos <= 0.0) {
            this._pulsePos = 0.0;
            this._pulseDir = 1;
        }
        this.queue_repaint();
    }

    addLevel(level) {
        this._levels.shift();
        this._levels.push(level);
        this.queue_repaint();
    }

    vfunc_repaint() {
        let cr = this.get_context();
        let [width, height] = this.get_surface_size();
        
        if (this._isIndeterminate) {
            let pulseWidth = width * 0.4;
            let startX = (width - pulseWidth) * this._pulsePos;
            
            cr.setSourceRGBA(1.0, 1.0, 1.0, 0.2);
            cr.setLineWidth(3.0);
            cr.setLineCap(1);
            cr.moveTo(0, height / 2);
            cr.lineTo(width, height / 2);
            cr.stroke();

            cr.setSourceRGBA(0.2, 0.6, 1.0, 0.95);
            cr.setLineWidth(3.5);
            cr.moveTo(startX, height / 2);
            cr.lineTo(startX + pulseWidth, height / 2);
            cr.stroke();
            return;
        }

        cr.setSourceRGBA(1.0, 1.0, 1.0, 0.7);
        cr.setLineWidth(2.0);
        cr.setLineCap(1); // ROUND
        
        let step = width / (this._levels.length - 1);
        
        for (let i = 0; i < this._levels.length; i++) {
            let val = this._levels[i] * (height / 2);
            let x = i * step;
            let y1 = (height / 2) - val;
            let y2 = (height / 2) + val;
            if (val < 0.5) {
                y1 = (height / 2) - 0.5;
                y2 = (height / 2) + 0.5;
            }
            cr.moveTo(x, y1);
            cr.lineTo(x, y2);
        }
        cr.stroke();
    }
});

const OpenDictateIndicator = GObject.registerClass(
class OpenDictateIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'OpenDictate');
        
        this._box = new St.BoxLayout({ style_class: 'opendictate-box' });
        
        // Gear Icon & Button for menu
        this._gearIcon = new St.Icon({
            icon_name: 'emblem-system-symbolic',
            icon_size: 16,
            style_class: 'opendictate-icon',
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._gearButton = new St.Button({
            child: this._gearIcon,
            style_class: 'opendictate-action-button',
            reactive: true,
            can_focus: true,
            track_hover: true,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._gearButton.connect('button-press-event', (actor, event) => {
            if (event.get_button() === 1) {
                this.menu.toggle();
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        
        // Microphone/Record Icon (Main Button)
        this._micIcon = new St.Icon({
            icon_name: 'audio-input-microphone-symbolic',
            icon_size: 16,
            style_class: 'opendictate-icon',
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._mainButton = new St.Button({
            child: this._micIcon,
            style_class: 'opendictate-action-button',
            reactive: true,
            can_focus: true,
            track_hover: true,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._mainButton.connect('button-press-event', (actor, event) => {
            if (event.get_button() === 1) { // Left click
                if (this._stateData && this._stateData.state === "RECORDING") {
                    this._sendCommand('pause');
                } else if (this._stateData && this._stateData.state === "PAUSED") {
                    this._sendCommand('record');
                } else if (this._stateData && (this._stateData.state === "TRANSCRIBING" || this._stateData.state === "CLEANING" || this._stateData.state === "PROCESSING")) {
                    this._sendCommand('cancel');
                } else {
                    this._sendCommand('record');
                }
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        
        // Waveform
        this._waveform = new Waveform();
        this._waveform.y_align = Clutter.ActorAlign.CENTER;
        
        // Time Label
        this._timeLabel = new St.Label({
            text: '00:00',
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'opendictate-time-label'
        });
        
        // Send Button
        this._sendButton = new St.Button({
            child: new St.Icon({
                icon_name: 'mail-send-symbolic',
                icon_size: 16,
                style_class: 'opendictate-icon opendictate-send-icon',
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            }),
            style_class: 'opendictate-action-button',
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            reactive: true,
            can_focus: true,
            track_hover: true,
        });
        this._sendButton.connect('button-press-event', (actor, event) => {
            if (event.get_button() === 1) {
                this._sendCommand('send');
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        
        // Cancel Button
        this._cancelButton = new St.Button({
            child: new St.Icon({
                icon_name: 'process-stop-symbolic',
                icon_size: 16,
                style_class: 'opendictate-icon opendictate-cancel-icon',
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            }),
            style_class: 'opendictate-action-button',
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            reactive: true,
            can_focus: true,
            track_hover: true,
        });
        this._cancelButton.connect('button-press-event', (actor, event) => {
            if (event.get_button() === 1) {
                this._sendCommand('cancel');
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        
        // Add children
        this._box.add_child(this._gearButton);
        this._box.add_child(this._mainButton);
        this._box.add_child(this._waveform);
        this._box.add_child(this._timeLabel);
        this._box.add_child(this._sendButton);
        this._box.add_child(this._cancelButton);
        
        this.add_child(this._box);
        
        this._waveform.hide();
        this._timeLabel.hide();
        this._sendButton.hide();
        this._cancelButton.hide();
        
        // Setup Context Menu
        this.autosendToggle = new PopupMenu.PopupSwitchMenuItem('Auto-Send (Enter)', false);
        this.autosendToggle.connect('toggled', () => {
            if (!this._updatingToggles) this._sendCommand('toggle-autosend');
        });
        this.menu.addMenuItem(this.autosendToggle);

        this.aiToggle = new PopupMenu.PopupSwitchMenuItem('AI Cleanup', false);
        this.aiToggle.connect('toggled', () => {
            if (!this._updatingToggles) this._sendCommand('toggle-ai');
        });
        this.menu.addMenuItem(this.aiToggle);
        
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this.settingsItem = new PopupMenu.PopupMenuItem('Settings');
        this.settingsItem.connect('activate', () => {
            this._sendCommand('settings');
        });
        this.menu.addMenuItem(this.settingsItem);
        
        this.quitItem = new PopupMenu.PopupMenuItem('Quit OpenDictate');
        this.quitItem.connect('activate', () => {
            this._sendCommand('quit');
        });
        this.menu.addMenuItem(this.quitItem);
        
        this._stateData = null;
        this._timerId = null;
        this._indeterminateTimerId = null;
        this._targetWindow = null;
        this._previousState = null;
        
        this._monitorStateFile();
    }
    
    _sendCommand(cmd) {
        if (cmd === 'record') {
            this._targetWindow = this._captureFocusWindow();
        }
        try {
            let client = new Gio.SocketClient();
            let address = Gio.UnixSocketAddress.new(SOCKET_PATH);
            client.connect_async(address, null, (client, res) => {
                try {
                    let connection = client.connect_finish(res);
                    let output = connection.get_output_stream();
                    output.write_bytes_async(new GLib.Bytes(cmd), GLib.PRIORITY_DEFAULT, null, (stream, res2) => {
                        stream.write_bytes_finish(res2);
                        connection.close(null);
                    });
                } catch (e) {
                    console.error(`OpenDictate: Socket error sending ${cmd}: ${e.message}`);
                    if (cmd !== 'quit') {
                        this._ensureDaemonRunning();
                    }
                }
            });
        } catch (e) {
            console.error(`OpenDictate: Socket setup error: ${e.message}`);
            if (cmd !== 'quit') {
                this._ensureDaemonRunning();
            }
        }
    }

    _ensureDaemonRunning() {
        try {
            let daemonBin = `${GLib.get_home_dir()}/.local/share/dictate-whisper/.venv/bin/python`;
            let daemonScript = `${GLib.get_home_dir()}/.local/share/dictate-whisper/dictate-daemon.py`;
            if (GLib.file_test(daemonScript, GLib.FileTest.EXISTS)) {
                GLib.spawn_command_line_async(`${daemonBin} ${daemonScript} --force-start`);
            }
        } catch (e) {
            console.error(`OpenDictate: Failed to auto-start daemon: ${e.message}`);
        }
    }
    
    _updateUI(stateData) {
        this._stateData = stateData;
        let state = stateData.state || "IDLE";
        
        this._updatingToggles = true;
        if (stateData.autosend_enabled !== undefined && this.autosendToggle.state !== stateData.autosend_enabled) {
            this.autosendToggle.setToggleState(stateData.autosend_enabled);
        }
        if (stateData.ai_enabled !== undefined && this.aiToggle.state !== stateData.ai_enabled) {
            this.aiToggle.setToggleState(stateData.ai_enabled);
        }
        this._updatingToggles = false;
        
        let icon = this._micIcon;
        
        if (state === "RECORDING") {
            if (this._previousState !== "RECORDING") {
                this._targetWindow = this._captureFocusWindow();
            }
            this._stopIndeterminateTimer();
            this._waveform.setIndeterminate(false);
            icon.icon_name = 'media-record-symbolic';
            icon.add_style_class_name('recording');
            icon.remove_style_class_name('paused');
            icon.remove_style_class_name('processing');
            
            this._waveform.show();
            if (stateData.level !== undefined) {
                this._waveform.addLevel(stateData.level);
            }
            
            this._timeLabel.show();
            this._sendButton.show();
            this._cancelButton.show();
            this._startTimer();
            
        } else if (state === "PAUSED") {
            this._stopIndeterminateTimer();
            this._waveform.setIndeterminate(false);
            icon.icon_name = 'media-playback-pause-symbolic';
            icon.remove_style_class_name('recording');
            icon.add_style_class_name('paused');
            icon.remove_style_class_name('processing');
            
            this._waveform.show();
            this._timeLabel.show();
            this._sendButton.show();
            this._cancelButton.show();
            this._stopTimer();
            this._updateTimeDisplay();
            
        } else if (state === "LOADING" || state === "PREVIEW" || state === "CLEANING" || state === "PROCESSING" || state === "TRANSCRIBING") {
            icon.icon_name = 'audio-input-microphone-symbolic';
            icon.remove_style_class_name('recording');
            icon.remove_style_class_name('paused');
            icon.add_style_class_name('processing');
            
            this._waveform.setIndeterminate(true);
            this._waveform.show();
            this._startIndeterminateTimer();
            
            let statusText = stateData.status_text;
            if (!statusText) {
                let lang = stateData.ui_language || "en";
                if (lang === "es") {
                    statusText = state === "TRANSCRIBING" ? "Transcribiendo..." : (state === "CLEANING" ? "Limpiando..." : "Procesando...");
                } else if (lang === "de") {
                    statusText = state === "TRANSCRIBING" ? "Transkribieren..." : (state === "CLEANING" ? "Text bereinigen..." : "Verarbeitung...");
                } else if (lang === "fr") {
                    statusText = state === "TRANSCRIBING" ? "Transcription..." : (state === "CLEANING" ? "Nettoyage..." : "Traitement...");
                } else {
                    statusText = state === "TRANSCRIBING" ? "Transcribing..." : (state === "CLEANING" ? "Cleaning text..." : "Processing...");
                }
            }
            this._timeLabel.set_text(statusText);
            this._timeLabel.show();
            this._sendButton.hide();
            this._cancelButton.show();
            this._stopTimer();
        } else {
            this._stopIndeterminateTimer();
            this._waveform.setIndeterminate(false);
            icon.icon_name = 'audio-input-microphone-symbolic';
            icon.remove_style_class_name('recording');
            icon.remove_style_class_name('paused');
            icon.remove_style_class_name('processing');
            
            this._waveform.hide();
            this._timeLabel.hide();
            this._sendButton.hide();
            this._cancelButton.hide();
            this._stopTimer();
        }

        if ((stateData.send_status === "pasting" || (this._previousState && this._previousState !== "IDLE" && state === "IDLE")) && stateData.restore_window_focus) {
            if (this._targetWindow) {
                try {
                    this._targetWindow.activate(global.get_current_time());
                } catch (e) {
                    console.error(`OpenDictate: Failed to activate target window: ${e.message}`);
                }
                this._targetWindow = null;
            }
        }

        this._previousState = state;
    }

    _captureFocusWindow() {
        try {
            let win = global.display ? global.display.focus_window : null;
            if (win && win.get_window_type() === Meta.WindowType.NORMAL) {
                return win;
            }
            let workspace = global.workspace_manager ? global.workspace_manager.get_active_workspace() : null;
            if (workspace) {
                let windows = workspace.list_windows();
                for (let w of windows) {
                    if (w.get_window_type() === Meta.WindowType.NORMAL && w.has_focus()) {
                        return w;
                    }
                }
                for (let w of windows) {
                    if (w.get_window_type() === Meta.WindowType.NORMAL && !w.is_hidden()) {
                        return w;
                    }
                }
            }
            return win;
        } catch (e) {
            console.error(`OpenDictate: Error capturing window: ${e.message}`);
            return null;
        }
    }
    
    _updateTimeDisplay() {
        if (!this._stateData || !this._stateData.start_time) return;
        
        let elapsed = 0;
        let nowSecs = GLib.get_real_time() / 1000000;
        
        if (this._stateData.state === "RECORDING") {
            elapsed = nowSecs - this._stateData.start_time - (this._stateData.total_paused_time || 0);
        } else if (this._stateData.state === "PAUSED") {
            elapsed = (this._stateData.pause_start_time || nowSecs) - this._stateData.start_time - (this._stateData.total_paused_time || 0);
        }
        
        if (elapsed < 0) elapsed = 0;
        
        let mins = Math.floor(elapsed / 60);
        let secs = Math.floor(elapsed % 60);
        let timeStr = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        this._timeLabel.set_text(timeStr);
    }
    
    _startTimer() {
        if (!this._timerId) {
            this._updateTimeDisplay();
            this._timerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
                this._updateTimeDisplay();
                return GLib.SOURCE_CONTINUE;
            });
        }
    }
    
    _stopTimer() {
        if (this._timerId) {
            GLib.Source.remove(this._timerId);
            this._timerId = null;
        }
    }

    _startIndeterminateTimer() {
        if (!this._indeterminateTimerId) {
            this._indeterminateTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 40, () => {
                this._waveform.updatePulse();
                return GLib.SOURCE_CONTINUE;
            });
        }
    }
    
    _stopIndeterminateTimer() {
        if (this._indeterminateTimerId) {
            GLib.Source.remove(this._indeterminateTimerId);
            this._indeterminateTimerId = null;
        }
    }
    
    _readStateFile() {
        let file = Gio.File.new_for_path(STATE_FILE);
        if (!file.query_exists(null)) return;
        
        try {
            let [, contents] = file.load_contents(null);
            let stateData = JSON.parse(new TextDecoder().decode(contents));
            this._updateUI(stateData);
        } catch (e) {
            console.error(`OpenDictate: Error reading state file: ${e.message}`);
        }
    }
    
    _monitorStateFile() {
        let file = Gio.File.new_for_path(STATE_FILE);
        try {
            this._monitor = file.monitor_file(Gio.FileMonitorFlags.NONE, null);
            this._monitor.connect('changed', (monitor, file, otherFile, eventType) => {
                if (eventType === Gio.FileMonitorEvent.CHANGES_DONE_HINT || eventType === Gio.FileMonitorEvent.CREATED || eventType === Gio.FileMonitorEvent.CHANGED) {
                    this._readStateFile();
                }
            });
        } catch (e) {
            console.error(`OpenDictate: Error monitoring state file: ${e.message}`);
        }
        this._readStateFile();
    }
    
    destroy() {
        this._stopTimer();
        this._stopIndeterminateTimer();
        if (this._monitor) {
            this._monitor.cancel();
            this._monitor = null;
        }
        super.destroy();
    }
});

export default class OpenDictateExtension extends Extension {
    enable() {
        this._indicator = new OpenDictateIndicator();
        Main.panel.addToStatusArea(this.uuid, this._indicator, 1, 'center');
    }

    disable() {
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }
}

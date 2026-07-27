#!/home/butcherwutcher/.local/share/dictate-whisper/.venv/bin/python

import os
# Force X11 backend to bypass Wayland's strict always-on-top limitations
os.environ["GDK_BACKEND"] = "x11"
import sys
import socket
import threading
import subprocess
import signal
import time
import re
import shutil
import math
import struct
import cairo
import json
import logging
import numpy as np
import sqlite3
import keyring
import datetime
import dbus
import logging
import os
from logging.handlers import RotatingFileHandler
from i18n import get_translator

LOG_FILE = os.path.expanduser("~/.local/share/dictate-whisper/daemon.log")
logging.basicConfig(
    handlers=[RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=1)],
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True
)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

try:
    gi.require_foreign("cairo")
except ImportError as e:
    logging.error(f"Missing gi._gi_cairo module. Please run 'sudo apt install python3-gi-cairo'. Error: {e}")

try:
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
    HAS_INDICATOR = True
except (ValueError, ImportError):
    HAS_INDICATOR = False

SOCKET_PATH = "/tmp/dictate_daemon.socket"
AUDIO_FILE = "/tmp/dictate_recording.wav"
CONFIG_PATH = os.path.expanduser("~/.config/dictate-whisper/config.json")
DEFAULT_CONFIG = {
    "api_key": "",
    "llm_enabled": False,
    "model": "gemma-4"
}

class DictationDaemon:
    def __init__(self):
        self.base_dir = os.path.expanduser("~/.local/share/dictate-whisper")
        self.init_database()
        self.config = self.load_config()
        self.i18n = get_translator(self.config.get("ui_language", "en"))
        self.model_size = self.config.get("whisper_model_size", "medium")
        self.model = None
        self.config_window = None
        self.state = "IDLE"  
        self.next_action = None
        self.record_proc = None
        self.audio_file_handle = None
        self.start_time = 0
        self.total_paused_time = 0
        self.pause_start_time = 0
        self.timer_id = None
        self.current_text = ""
        self.audio_buffer = bytearray()
        self.paused_mpris_players = []
        self.confirmed_text = ""
        self.last_transcribed_time = 0.0
        
        self.init_database()
        self.setup_ui()
        self.setup_indicator()
        
        self.server_thread = threading.Thread(target=self.socket_server, daemon=True)
        self.server_thread.start()
        
        self.load_model_async(self.model_size)

    def load_config(self):
        cfg = DEFAULT_CONFIG.copy()
        
        # Migración desde config.json si existe
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    old_cfg = json.load(f)
                
                # Migrar API Key a keyring
                if "api_key" in old_cfg and old_cfg["api_key"]:
                    keyring.set_password("OpenDictate", "api_key", old_cfg["api_key"])
                    del old_cfg["api_key"]
                
                # Migrar resto a DB
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                for k, v in old_cfg.items():
                    cursor.execute("INSERT OR REPLACE INTO global_settings (key, value) VALUES (?, ?)", (k, json.dumps(v)))
                conn.commit()
                conn.close()
                
                # Eliminar config.json antiguo
                os.remove(CONFIG_PATH)
            except Exception as e:
                logging.error(f"Error migrando config.json: {e}")

        # Cargar de DB
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM global_settings")
            for row in cursor.fetchall():
                cfg[row[0]] = json.loads(row[1])
            conn.close()
        except Exception as e:
            logging.error(f"Error cargando configuracion desde DB: {e}")

        # Cargar API Key desde keyring
        try:
            stored_key = keyring.get_password("OpenDictate", "api_key")
            cfg["api_key"] = stored_key if stored_key else ""
        except Exception:
            cfg["api_key"] = ""
            
        return cfg

    def save_config(self):
        # Guardar API key en keyring y eliminar de self.config temporalmente para no guardarlo en la DB
        api_key = self.config.get("api_key", "")
        if api_key:
            keyring.set_password("OpenDictate", "api_key", api_key)
        else:
            try:
                keyring.delete_password("OpenDictate", "api_key")
            except:
                pass
                
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            for k, v in self.config.items():
                if k != "api_key":
                    cursor.execute("INSERT OR REPLACE INTO global_settings (key, value) VALUES (?, ?)", (k, json.dumps(v)))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error guardando configuracion en DB: {e}")

        if hasattr(self, 'config_window') and self.config_window:
            GLib.idle_add(self.config_window.update_ui_from_config, self.config)

    def init_database(self):
        self.db_path = os.path.join(self.base_dir, "dictate.db")
        try:
            os.makedirs(self.base_dir, exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS app_profiles (
                    app_class TEXT PRIMARY KEY,
                    system_prompt TEXT,
                    enable_vision BOOLEAN DEFAULT 0
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    app_class TEXT,
                    window_title TEXT,
                    original_text TEXT,
                    llm_text TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS global_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            logging.info("Base de datos SQLite inicializada.")
        except Exception as e:
            logging.error(f"Error inicializando base de datos: {e}")

    def get_active_window_info(self):
        try:
            import pyatspi
            desktop = pyatspi.Registry.getDesktop(0)
            for app in desktop:
                if not app: continue
                for window in app:
                    if not window: continue
                    state = window.getState()
                    if state.contains(pyatspi.STATE_ACTIVE):
                        return app.name, window.name
            return "unknown", "unknown"
        except ImportError:
            logging.warning("pyatspi no está instalado. Ejecuta: sudo apt install python3-pyatspi")
            return "unknown", "unknown"
        except Exception as e:
            logging.error(f"Error obteniendo ventana activa: {e}")
            return "unknown", "unknown"

    def export_state(self):
        try:
            with open("/tmp/dictate_state.json", "w") as f:
                json.dump({
                    "state": self.state, 
                    "model": self.model_size,
                    "start_time": getattr(self, 'start_time', 0),
                    "pause_start_time": getattr(self, 'pause_start_time', 0),
                    "total_paused_time": getattr(self, 'total_paused_time', 0)
                }, f)
        except Exception as e:
            logging.error(f"Error exporting state: {e}")

    def show_notification(self, title, message, timeout=1500):
        if not self.config.get("show_notifications", True):
            return
        try:
            subprocess.Popen([
                "notify-send", 
                "-h", "string:x-canonical-private-synchronous:dictate", 
                "-t", str(timeout), 
                title, 
                message
            ])
        except Exception as e:
            logging.error(f"Error showing notification: {e}")

    def show_error_notification(self, title, message):
        self.show_notification(title, message, timeout=5000)

    def play_sound(self, sound_path):
        if os.path.exists(sound_path):
            subprocess.Popen(["pw-play", sound_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def on_window_button_press(self, widget, event):
        # Evitar capturar clics si caen directamente en botones o similares
        if event.button == 1:
            self.window.begin_move_drag(event.button, event.x_root, event.y_root, event.time)
            return False # allow buttons to receive click if we clicked exactly on a button
        elif event.button == 3:
            self.window.begin_resize_drag(Gdk.WindowEdge.SOUTH_EAST, event.button, event.x_root, event.y_root, event.time)
            return False
        return False

    def setup_ui(self):
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_decorated(False)
        self.window.set_keep_above(True)
        self.window.set_accept_focus(False)
        self.window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        
        # Restore position and size
        saved_x = self.config.get("window_x", -1)
        saved_y = self.config.get("window_y", -1)
        saved_w = self.config.get("window_width", -1)
        saved_h = self.config.get("window_height", -1)
        
        if saved_x != -1 and saved_y != -1:
            self.window.move(saved_x, saved_y)
        else:
            self.window.set_position(Gtk.WindowPosition.CENTER)
            
        if saved_w != -1 and saved_h != -1:
            self.window.resize(saved_w, saved_h)
            
        self.window.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.window.connect("button-press-event", self.on_window_button_press)
        
        screen = self.window.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.window.set_visual(visual)
        self.window.set_app_paintable(True)
        
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.box.set_name("bubble-window")
        
        self.status_icon = Gtk.Label(label="⚪")
        self.status_icon.set_name("status-icon")
        self.status_icon.set_halign(Gtk.Align.CENTER)
        
        self.time_label = Gtk.Label(label="00:00")
        self.time_label.set_name("time-label")
        self.time_label.set_halign(Gtk.Align.CENTER)
        
        self.level_bar = Gtk.LevelBar()
        self.level_bar.set_name("level-bar")
        self.level_bar.set_min_value(0.0)
        self.level_bar.set_max_value(1.0)
        self.level_bar.set_size_request(150, 8)

        self.text_buffer = Gtk.TextBuffer()
        self.text_view = Gtk.TextView(buffer=self.text_buffer)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_name("preview-text")
        
        self.text_view_scroll = Gtk.ScrolledWindow()
        self.text_view_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.text_view_scroll.set_min_content_height(100)
        self.text_view_scroll.set_min_content_width(300)
        self.text_view_scroll.add(self.text_view)
        
        self.button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.button_box.set_halign(Gtk.Align.CENTER)
        
        btn_close = Gtk.Button(label="❌")
        btn_close.set_tooltip_text(self.i18n.t("close"))
        btn_close.connect("clicked", lambda w: self.action_cancel())
        
        btn_copy = Gtk.Button(label="📋")
        btn_copy.set_tooltip_text(self.i18n.t("copy_clipboard"))
        btn_copy.connect("clicked", self.execute_copy)
        
        btn_insert = Gtk.Button(label="📝")
        btn_insert.set_tooltip_text(self.i18n.t("insert_text"))
        btn_insert.connect("clicked", lambda w: self.action_finish_normal())
        
        self.button_box.pack_start(btn_close, False, False, 0)
        self.button_box.pack_start(btn_copy, False, False, 0)
        self.button_box.pack_start(btn_insert, False, False, 0)
        
        self.box.pack_start(self.status_icon, False, False, 0)
        self.box.pack_start(self.text_view_scroll, True, True, 0)
        self.box.pack_start(self.time_label, False, False, 0)
        self.box.pack_start(self.level_bar, False, False, 0)
        self.box.pack_start(self.button_box, False, False, 0)
        
        self.window.add(self.box)
        
        css_provider = Gtk.CssProvider()
        css = b"""
        #bubble-window {
            background-color: rgba(30, 30, 30, 0.95);
            padding: 20px 30px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
        }
        #status-icon {
            font-size: 36px;
        }
        #time-label {
            color: #aaaaaa;
            font-size: 14px;
        }
        #preview-text, textview text, textview {
            background-color: transparent;
            color: white;
            font-size: 16px;
        }
        scrolledwindow {
            background-color: transparent;
        }
        #level-bar block.filled {
            background-color: #4CAF50;
            border-radius: 2px;
        }
        #level-bar.transcribing block.filled {
            background-color: #2196F3;
        }
        #level-bar.cleaning block.filled {
            background-color: #9C27B0;
        }
        button {
            padding: 8px 12px;
            border-radius: 6px;
            background-color: rgba(255,255,255,0.1);
            color: white;
            border: none;
        }
        button:hover {
            background-color: rgba(255,255,255,0.2);
        }
        scrollbar, scrollbar trough, scrollbar slider {
            min-width: 0px;
            min-height: 0px;
            background-color: transparent;
            background: transparent;
            border: none;
        }
        """
        css_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            screen,
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.window.connect("draw", self.on_draw)

    def on_draw(self, widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)
        cr.paint()
        return False
        
    def setup_indicator(self):
        try:
            if not self.config.get("use_appindicator", True):
                return
            if HAS_INDICATOR:
                self.indicator = AppIndicator.Indicator.new(
                    "dictate-daemon",
                    "audio-input-microphone",
                    AppIndicator.IndicatorCategory.APPLICATION_STATUS
                )
                self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            
            self.build_menu()
        except Exception as e:
            logging.error(f"Error setting up indicator: {e}")

    def build_menu(self):
        menu = Gtk.Menu()
        
        self.status_menu_item = Gtk.MenuItem(label=self.i18n.t("loading_model"))
        self.status_menu_item.set_sensitive(False)
        menu.append(self.status_menu_item)
        menu.append(Gtk.SeparatorMenuItem())
        
        # Model size submenu
        model_menu_item = Gtk.MenuItem(label=self.i18n.t("whisper_model"))
        model_submenu = Gtk.Menu()
        model_menu_item.set_submenu(model_submenu)
        
        self.model_radios = {}
        group = None
        for size in ["tiny", "base", "small", "medium", "large-v3"]:
            radio = Gtk.RadioMenuItem.new_with_label(group, size)
            group = radio.get_group()
            if self.model_size == size:
                radio.set_active(True)
            radio.connect('toggled', self.on_model_changed, size)
            self.model_radios[size] = radio
            model_submenu.append(radio)
            
        menu.append(model_menu_item)
        menu.append(Gtk.SeparatorMenuItem())
        
        self.auto_send_check = Gtk.CheckMenuItem(label=self.i18n.t("auto_send"))
        self.auto_send_check.set_active(self.config.get("auto_send", False))
        self.auto_send_check.connect("toggled", self.on_auto_send_toggled_from_ui)
        menu.append(self.auto_send_check)
        
        self.ai_check = Gtk.CheckMenuItem(label=self.i18n.t("ai_cleanup"))
        self.ai_check.set_active(self.config.get("ai_enabled", False))
        self.ai_check.connect("toggled", self.on_ai_toggled_from_ui)
        menu.append(self.ai_check)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        import os
        opendeck_plugin_path = os.path.expanduser("~/.config/opendeck/plugins/com.kirulab.dictate.sdplugin")
        plugin_installed = os.path.exists(opendeck_plugin_path)
        
        opendeck_label = self.i18n.t("opendeck_installed") if plugin_installed else self.i18n.t("opendeck_not_installed")
        item_opendeck = Gtk.MenuItem(label=opendeck_label)
        item_opendeck.connect('activate', self.install_opendeck_plugin)
        menu.append(item_opendeck)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        item_config = Gtk.MenuItem(label=self.i18n.t("settings"))
        item_config.connect('activate', self.open_config_window)
        menu.append(item_config)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        item_quit = Gtk.MenuItem(label=self.i18n.t("quit"))
        item_quit.connect('activate', Gtk.main_quit)
        menu.append(item_quit)
        
        menu.show_all()
        if HAS_INDICATOR and hasattr(self, 'indicator'):
            self.indicator.set_menu(menu)
            
        # Actualizar estado del menu si el daemon ya esta listo
        if self.state not in ["LOADING", "IDLE"] and hasattr(self, 'status_menu_item'):
            self.status_menu_item.set_label(self.state)


            
    def open_config_window(self, widget=None):
        if getattr(self, 'config_window', None):
            self.config_window.update_ui_from_config(self.config)
            self.config_window.present()
            return
            
        try:
            from dictate_config_ui import ConfigWindow
            self.config_window = ConfigWindow(self.db_path, CONFIG_PATH, on_config_saved=self.on_config_saved, daemon_ref=self)
            self.config_window.connect("destroy", self.on_config_window_closed)
            self.config_window.show_all()
        except Exception as e:
            logging.error(f"Error opening config window: {e}", exc_info=True)
            self.show_error_notification(self.i18n.t("error"), self.i18n.t("error_opening_config"))

    def restart_config_window(self):
        if self.config_window:
            self.config_window.destroy()
            self.config_window = None
            GLib.idle_add(self.open_config_window)

    def on_config_window_closed(self, widget):
        self.config_window = None

    def on_config_saved(self, new_config=None):
        old_model = self.config.get("whisper_model_size") if hasattr(self, 'config') else None
        
        if new_config is not None:
            self.config = new_config
            self.save_config()
        else:
            self.config = self.load_config()
            
        new_model = self.config.get("whisper_model_size")
        
        self.i18n = get_translator(self.config.get("ui_language", "en"))
        self.build_menu()
        if hasattr(self, 'auto_send_check'):
            self.auto_send_check.set_active(self.config.get("auto_send", False))
        if hasattr(self, 'ai_check'):
            self.ai_check.set_active(self.config.get("ai_enabled", False))
        logging.info("Configuración recargada.")
        self.export_state()
        
        if old_model and new_model and old_model != new_model:
            if self.state == "IDLE":
                self.load_model_async(new_model)


    def on_auto_send_toggled_from_ui(self, widget):
        if self.config.get("auto_send", False) != widget.get_active():
            self.config["auto_send"] = widget.get_active()
            self.save_config()
            logging.info(f"Auto-send set to {self.config['auto_send']} via UI.")
            self.export_state()

    def on_ai_toggled_from_ui(self, widget):
        if self.config.get("ai_enabled", False) != widget.get_active():
            self.config["ai_enabled"] = widget.get_active()
            self.save_config()
            logging.info(f"AI enabled set to {self.config['ai_enabled']} via UI.")
            self.export_state()

    def install_opendeck_plugin(self, widget):
        import shutil
        import subprocess
        opendeck_plugins_dir = os.path.expanduser("~/.config/opendeck/plugins/")
        plugin_name = "com.kirulab.dictate.sdplugin"
        target_dir = os.path.join(opendeck_plugins_dir, plugin_name)
        source_dir = os.path.join(os.path.dirname(__file__), "plugins", plugin_name)
        
        try:
            os.makedirs(opendeck_plugins_dir, exist_ok=True)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            if os.path.exists(source_dir):
                shutil.copytree(source_dir, target_dir)
                logging.info(f"Plugin copied to {target_dir}")
                
                # Restart OpenDeck quietly
                subprocess.run(["pkill", "-9", "opendeck"])
                subprocess.Popen(["/usr/bin/opendeck", "--hide"], start_new_session=True)
                
                self.show_error_notification(self.i18n.t("opendeck"), self.i18n.t("opendeck_installed_success"))
                
                # Update menu label
                if hasattr(self, "indicator"):
                    widget.set_label(self.i18n.t("opendeck_installed"))
            else:
                self.show_error_notification(self.i18n.t("error"), self.i18n.t("error_plugin_not_found"))
        except Exception as e:
            logging.error(f"Error installing plugin: {e}", exc_info=True)
            self.show_error_notification(self.i18n.t("error"), str(e))

    def action_send(self):
        if self.config.get("ai_enabled", False):
            self.action_finish_ai()
        else:
            self.action_finish_normal()

    def action_cycle_model(self):
        models = ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"]
        try:
            idx = models.index(self.model_size)
            next_model = models[(idx + 1) % len(models)]
        except ValueError:
            next_model = "small"
        
        # update radio button if any (this triggers on_model_changed)
        for r in self.radios:
            if r.get_label() == next_model:
                r.set_active(True)
                break
        else:
            self.load_model_async(next_model)

    def action_toggle_ai(self):
        new_state = not self.config.get("ai_enabled", False)
        self.config["ai_enabled"] = new_state
        self.save_config()
        if hasattr(self, 'ai_check'):
            self.ai_check.set_active(new_state)
        self.export_state()
        self.show_notification("OpenDictate", self.i18n.t("ai_enabled") if new_state else self.i18n.t("ai_disabled"))

    def action_toggle_autosend(self):
        new_state = not self.config.get("auto_send", False)
        self.config["auto_send"] = new_state
        self.save_config()
        if hasattr(self, 'auto_send_check'):
            self.auto_send_check.set_active(new_state)
        self.export_state()
        self.show_notification("OpenDictate", self.i18n.t("autosend_enabled") if new_state else self.i18n.t("autosend_disabled"))

    def action_toggle_realtime(self):
        new_state = not self.config.get("realtime_mode", True)
        self.config["realtime_mode"] = new_state
        self.save_config()
        if hasattr(self, 'realtime_switch'):
            self.realtime_switch.set_active(new_state)
        self.export_state()
        self.show_notification("OpenDictate", self.i18n.t("realtime_enabled") if new_state else self.i18n.t("realtime_disabled"))

    def action_autosend_activate(self):
        self.config["auto_send"] = True
        self.save_config()
        if hasattr(self, 'auto_send_check'):
            self.auto_send_check.set_active(True)
        self.export_state()
        self.show_notification("OpenDictate", self.i18n.t("autosend_enabled"))
        
    def action_autosend_deactivate(self):
        self.config["auto_send"] = False
        self.save_config()
        if hasattr(self, 'auto_send_check'):
            self.auto_send_check.set_active(False)
        self.export_state()
        self.show_notification("OpenDictate", self.i18n.t("autosend_disabled"))

    def update_tray_status(self, text):
        logging.info(f"State Update: {text}")
        if hasattr(self, 'status_menu_item'):
            self.status_menu_item.set_label(text)
        if hasattr(self, 'indicator'):
            if self.state == "RECORDING":
                self.indicator.set_icon("media-record")
            elif self.state == "PAUSED":
                self.indicator.set_icon("media-playback-pause")
            else:
                self.indicator.set_icon("audio-input-microphone")

    def load_model_async(self, size):
        old_size = getattr(self, 'model_size', 'medium')
        self.model_size = size
        self.state = "LOADING"
        self.update_tray_status(self.i18n.t("loading_model_param").format(size=size))
        self.export_state()
        
        def loader():
            from faster_whisper import WhisperModel
            try:
                new_model = WhisperModel(size, device="cpu", compute_type="int8")
                GLib.idle_add(self.on_model_loaded, new_model, size)
            except Exception as e:
                GLib.idle_add(self.on_model_error, str(e), old_size)
                
        threading.Thread(target=loader, daemon=True).start()

    def on_model_loaded(self, new_model, size):
        logging.info(f"Model loaded successfully: {size}")
        self.model = new_model
        self.model_size = size
        self.config["whisper_model_size"] = size
        self.save_config()
        self.reset_state()
        
    def on_model_error(self, err, old_size):
        self.model_size = old_size
        self.state = "IDLE"
        self.update_tray_status(self.i18n.t("error_loading_model"))
        self.show_error_notification(self.i18n.t("error_whisper"), str(err))
        self.export_state()

    def on_model_changed(self, radio, size):
        if radio.get_active() and size != self.model_size:
            if self.state == "IDLE":
                self.load_model_async(size)
            else:
                radio.set_active(False)
                
    def socket_server(self):
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_PATH)
        server.listen(5)
        
        while True:
            try:
                conn, addr = server.accept()
                data = conn.recv(1024).decode('utf-8').strip()
                conn.close()
                
                if not data:
                    continue
                    
                logging.info(f"Received socket command: {data}")
                
                if data == "record":
                    GLib.idle_add(self.action_record)
                elif data == "pause":
                    GLib.idle_add(self.action_pause)
                elif data == "cancel":
                    GLib.idle_add(self.action_cancel)
                elif data == "preview":
                    GLib.idle_add(self.action_preview)
                elif data == "send":
                    GLib.idle_add(self.action_send)
                elif data == "cycle-model":
                    GLib.idle_add(self.action_cycle_model)
                elif data == "toggle-ai":
                    GLib.idle_add(self.action_toggle_ai)
                elif data == "toggle-autosend":
                    GLib.idle_add(self.action_toggle_autosend)
                elif data in ["toggle-realtime", "toggle_realtime"]:
                    GLib.idle_add(self.action_toggle_realtime)
                elif data == "toggle-autopause":
                    val = not self.config.get("auto_pause_media", True)
                    self.config["auto_pause_media"] = val
                    self.save_config()
                    self.export_state()
                    GLib.idle_add(self.show_notification, "OpenDictate", self.i18n.t("autopause_enabled") if val else self.i18n.t("autopause_disabled"))
                elif data == "toggle-bubble":
                    val = not self.config.get("hide_bubble", False)
                    self.config["hide_bubble"] = val
                    self.save_config()
                    self.export_state()
                    GLib.idle_add(self.show_notification, "OpenDictate", self.i18n.t("bubble_hidden") if val else self.i18n.t("bubble_visible"))
                elif data == "toggle-record-send":
                    GLib.idle_add(self.action_toggle_record_send)
                elif data == "finish-normal":
                    GLib.idle_add(self.action_finish_normal)
                elif data == "finish-ai":
                    GLib.idle_add(self.action_finish_ai)
                elif data == "quit":
                    GLib.idle_add(Gtk.main_quit)
                elif data == "settings":
                    GLib.idle_add(self.open_config_window)
            except Exception:
                pass

    def action_record(self):
        if self.state == "IDLE":
            self.start_recording()
        elif self.state == "PAUSED":
            self.total_paused_time += time.time() - self.pause_start_time
            self.record_proc.send_signal(signal.SIGCONT)
            self.state = "RECORDING"
            self.status_icon.set_text("🔴")
            self.update_tray_status(self.i18n.t("recording"))
            self.export_state()

    def action_pause(self):
        if self.state == "RECORDING":
            self.record_proc.send_signal(signal.SIGSTOP)
            self.state = "PAUSED"
            self.pause_start_time = time.time()
            self.status_icon.set_text("⏸️")
            self.update_tray_status(self.i18n.t("paused"))
            self.level_bar.set_value(0.0)
            self.export_state()

    def action_cancel(self):
        if self.state in ["RECORDING", "PAUSED"]:
            if self.state == "PAUSED":
                self.record_proc.send_signal(signal.SIGCONT)
            self.record_proc.send_signal(signal.SIGKILL)
            self.record_proc.wait()
            
            if self.audio_file_handle:
                self.audio_file_handle.close()
                
            self.resume_media()
                
            self.status_icon.set_text("❌")
            GLib.timeout_add(700, self.reset_state)
        elif self.state == "PREVIEW":
            self.reset_state()

    def action_preview(self):
        if self.state in ["RECORDING", "PAUSED"]:
            self.next_action = "PREVIEW"
            self.stop_recording()

    def action_finish_normal(self):
        if self.state in ["RECORDING", "PAUSED"]:
            self.next_action = "FINISH_NORMAL"
            self.stop_recording()
        elif self.state == "PREVIEW":
            self.execute_paste(self.current_text, self.config.get("auto_send", False))

    def action_finish_ai(self):
        if self.state in ["RECORDING", "PAUSED"]:
            self.next_action = "FINISH_AI"
            self.stop_recording()
        elif self.state == "PREVIEW":
            # Si estaba en preview ya está limpio (si el LLM estaba prendido globalmente), pero usamos el auto_send.
            self.execute_paste(self.current_text, self.config.get("auto_send", False))

    def action_toggle_record_send(self):
        if self.state == "IDLE":
            self.action_record()
        elif self.state in ["RECORDING", "PAUSED"]:
            if self.config.get("ai_enabled", False):
                self.action_finish_ai()
            else:
                self.action_finish_normal()

    def pause_media(self):
        if not self.config.get("auto_pause_media", True):
            return
        self.paused_mpris_players = []
        try:
            bus = dbus.SessionBus()
            for service in bus.list_names():
                if service.startswith('org.mpris.MediaPlayer2.'):
                    try:
                        player = bus.get_object(service, '/org/mpris/MediaPlayer2')
                        props = dbus.Interface(player, 'org.freedesktop.DBus.Properties')
                        status = props.Get('org.mpris.MediaPlayer2.Player', 'PlaybackStatus')
                        if status == 'Playing':
                            iface = dbus.Interface(player, 'org.mpris.MediaPlayer2.Player')
                            iface.Pause()
                            self.paused_mpris_players.append(service)
                            logging.info(f"Medio pausado automáticamente: {service}")
                    except Exception as e:
                        logging.warning(f"Error al pausar el medio {service}: {e}")
        except Exception as e:
            logging.error(f"Error en D-Bus al intentar pausar medios: {e}")

    def resume_media(self):
        try:
            bus = dbus.SessionBus()
            for service in self.paused_mpris_players:
                try:
                    player = bus.get_object(service, '/org/mpris/MediaPlayer2')
                    iface = dbus.Interface(player, 'org.mpris.MediaPlayer2.Player')
                    iface.Play()
                    logging.info(f"Medio reanudado automáticamente: {service}")
                except Exception as e:
                    logging.warning(f"Error al reanudar el medio {service}: {e}")
        except Exception as e:
            logging.error(f"Error en D-Bus al intentar reanudar medios: {e}")
        self.paused_mpris_players = []

    def start_recording(self):
        if self.state != "IDLE" or self.model is None:
            return
            
        self.pause_media()
        
        self.state = "RECORDING"
        self.update_tray_status(self.i18n.t("recording"))
        self.play_sound("/usr/share/sounds/freedesktop/stereo/device-added.oga")
        
        self.start_time = time.time()
        self.total_paused_time = 0
        self.pause_start_time = 0
        self.audio_buffer = bytearray()
        self.confirmed_text = ""
        self.last_transcribed_time = 0.0
        
        self.current_app_class, self.current_window_title = self.get_active_window_info()
        logging.info(f"Grabando en aplicación: {self.current_app_class} (Ventana: {self.current_window_title})")
        
        if not self.config.get("hide_bubble", False):
            self.window.show_all()
        self.text_view_scroll.show_all()
        self.text_buffer.set_text(self.i18n.t("recording"))
        self.button_box.hide()
        
        self.status_icon.show()
        self.time_label.show()
        self.level_bar.show()
        
        self.status_icon.set_text("🔴")
        self.time_label.set_text("00:00")
        self.level_bar.set_value(0.0)
        
        ctx = self.level_bar.get_style_context()
        ctx.remove_class("transcribing")
        ctx.remove_class("cleaning")
        
        if getattr(self, 'timer_id', None):
            try:
                GLib.source_remove(self.timer_id)
            except Exception:
                pass
            self.timer_id = None
        self.timer_id = GLib.timeout_add(100, self.update_timer)
        
        self.record_proc = subprocess.Popen(
            ["arecord", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", "16000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        self.audio_file_handle = open(AUDIO_FILE + ".pcm", "wb")
        threading.Thread(target=self.process_audio_stream, daemon=True).start()
        if self.config.get("realtime_mode", True):
            threading.Thread(target=self.streaming_transcriber_thread, daemon=True).start()

    def export_state(self):
        state_data = {
            "state": self.state,
            "time_str": getattr(self, "last_time_str", "00:00"),
            "model": self.model_size,
            "level": getattr(self, "audio_level", 0.0),
            "ai_enabled": self.config.get("ai_enabled", False),
            "autosend_enabled": self.config.get("auto_send", False),
            "autopause_enabled": self.config.get("auto_pause_media", True),
            "realtime_enabled": self.config.get("realtime_mode", True),
            "hide_bubble": self.config.get("hide_bubble", False),
            "send_status": getattr(self, "send_status", "idle"),
            "start_time": getattr(self, 'start_time', 0),
            "pause_start_time": getattr(self, 'pause_start_time', 0),
            "total_paused_time": getattr(self, 'total_paused_time', 0)
        }
        try:
            with open("/tmp/dictate_state.json", "w") as f:
                json.dump(state_data, f)
        except:
            pass

    def update_timer(self):
        if self.state in ["RECORDING", "PAUSED"]:
            if self.state == "RECORDING":
                elapsed = time.time() - self.start_time - self.total_paused_time
            else:
                elapsed = self.pause_start_time - self.start_time - self.total_paused_time
                
            mins = int(elapsed) // 60
            secs = int(elapsed) % 60
            self.last_time_str = f"{mins:02d}:{secs:02d}"
            self.time_label.set_text(self.last_time_str)
            self.export_state()
            return True
        elif self.state in ["TRANSCRIBING", "CLEANING"]:
            if hasattr(self, 'processing_start_time') and self.state == "CLEANING":
                elapsed = time.time() - self.processing_start_time
                mins = int(elapsed) // 60
                secs = int(elapsed) % 60
                self.last_time_str = f"{mins:02d}:{secs:02d}"
                self.time_label.set_text(self.last_time_str)
            self.export_state()
            return True
            
        self.timer_id = None
        return False

    def process_audio_stream(self):
        chunk_size = 1024
        while self.state in ["RECORDING", "PAUSED"]:
            data = self.record_proc.stdout.read(chunk_size)
            if not data:
                break
            self.audio_file_handle.write(data)
            self.audio_buffer.extend(data)
            
            if self.state == "RECORDING" and len(data) == chunk_size:
                try:
                    samples = struct.unpack(f"<{chunk_size//2}h", data)
                    sum_sq = sum(s*s for s in samples)
                    rms = math.sqrt(sum_sq / (chunk_size//2))
                    norm = min(1.0, rms / 4000.0)
                    self.audio_level = norm
                    self.export_state()
                    GLib.idle_add(self.level_bar.set_value, norm)
                except Exception:
                    pass
        
    def stop_recording(self):
        self.resume_media()
        self.state = "TRANSCRIBING"
        self.processing_start_time = time.time()
        self.update_tray_status(self.i18n.t("transcribing"))
        
        if self.record_proc:
            if self.record_proc.poll() is None:
                self.record_proc.send_signal(signal.SIGCONT)
                self.record_proc.terminate()
                try:
                    self.record_proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self.record_proc.kill()
        
        if self.audio_file_handle:
            self.audio_file_handle.close()
            
        self.play_sound("/usr/share/sounds/freedesktop/stereo/device-removed.oga")
        self.status_icon.set_text("🔄")
        
        ctx = self.level_bar.get_style_context()
        ctx.add_class("transcribing")
        self.level_bar.set_value(0.0)
        
        threading.Thread(target=self.transcribe_final_chunk, daemon=True).start()

    def update_live_text(self, text):
        self.text_buffer.set_text(text)
        
        def scroll_down():
            end_iter = self.text_buffer.get_end_iter()
            mark = self.text_buffer.create_mark(None, end_iter, False)
            self.text_view.scroll_mark_onscreen(mark)
            return False
            
        GLib.idle_add(scroll_down)

    def streaming_transcriber_thread(self):
        stride = 10.0
        overlap = 2.0
        sample_rate = 16000
        bytes_per_sec = sample_rate * 2
        
        while self.state in ["RECORDING", "PAUSED"]:
            current_audio_time = len(self.audio_buffer) / bytes_per_sec
            if current_audio_time >= self.last_transcribed_time + stride:
                chunk_start_time = max(0.0, self.last_transcribed_time - overlap)
                # Cap the chunk to stride+overlap to avoid massive chunks if falling behind
                chunk_end_time = min(current_audio_time, chunk_start_time + stride + overlap)
                
                start_idx = int(chunk_start_time * bytes_per_sec)
                end_idx = int(chunk_end_time * bytes_per_sec)
                
                chunk_bytes = self.audio_buffer[start_idx:end_idx]
                if len(chunk_bytes) % 2 != 0:
                    chunk_bytes = chunk_bytes[:-1]
                
                try:
                    audio_int16 = np.frombuffer(chunk_bytes, dtype=np.int16)
                    audio_float32 = audio_int16.astype(np.float32) / 32768.0
                    
                    initial_prompt = self.confirmed_text[-200:] if self.confirmed_text else None
                    
                    kwargs = {
                        "beam_size": self.config.get("beam_size", 5),
                        "word_timestamps": True,
                        "initial_prompt": initial_prompt,
                        "vad_filter": self.config.get("vad_filter", False)
                    }
                    
                    lang = self.config.get("language", "auto")
                    if lang != "auto":
                        kwargs["language"] = lang
                        
                    temp = self.config.get("temperature", 0.0)
                    if temp == 0.0:
                        kwargs["temperature"] = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
                    else:
                        kwargs["temperature"] = temp
                    
                    segments, info = self.model.transcribe(audio_float32, **kwargs)
                    
                    chunk_text = ""
                    for segment in segments:
                        for word in segment.words:
                            abs_time = chunk_start_time + word.start
                            if abs_time >= (self.last_transcribed_time - 0.4) and abs_time < (chunk_end_time - overlap):
                                chunk_text += word.word
                    
                    if chunk_text:
                        self.confirmed_text += chunk_text
                        GLib.idle_add(self.update_live_text, self.confirmed_text)
                    
                    self.last_transcribed_time = chunk_end_time - overlap
                    
                except Exception as e:
                    logging.error(f"Streaming transcription error: {e}", exc_info=True)
            
            time.sleep(0.5)

    def transcribe_final_chunk(self):
        logging.info("Starting final chunk transcription...")
        try:
            sample_rate = 16000
            bytes_per_sec = sample_rate * 2
            current_audio_time = len(self.audio_buffer) / bytes_per_sec
            
            if not self.config.get("realtime_mode", True):
                # Full Audio Batch Mode: transcribe entire audio_buffer at once
                logging.info("Executing full audio batch transcription...")
                chunk_bytes = bytes(self.audio_buffer)
                if len(chunk_bytes) % 2 != 0:
                    chunk_bytes = chunk_bytes[:-1]
                
                audio_int16 = np.frombuffer(chunk_bytes, dtype=np.int16)
                audio_float32 = audio_int16.astype(np.float32) / 32768.0
                
                kwargs = {
                    "beam_size": self.config.get("beam_size", 5),
                    "word_timestamps": True,
                    "vad_filter": self.config.get("vad_filter", False)
                }
                
                lang = self.config.get("language", "auto")
                if lang != "auto":
                    kwargs["language"] = lang
                    
                temp = self.config.get("temperature", 0.0)
                if temp == 0.0:
                    kwargs["temperature"] = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
                else:
                    kwargs["temperature"] = temp
                
                segments, info = self.model.transcribe(audio_float32, **kwargs)
                full_text = ""
                
                for segment in segments:
                    if current_audio_time > 0:
                        pct = segment.end / current_audio_time
                        pct = min(1.0, max(0.0, pct))
                        GLib.idle_add(self.level_bar.set_value, pct)
                    full_text += segment.text
                
                self.confirmed_text = full_text
            else:
                overlap = 2.0
                if current_audio_time > self.last_transcribed_time:
                    chunk_start_time = max(0.0, self.last_transcribed_time - overlap)
                    start_idx = int(chunk_start_time * bytes_per_sec)
                    chunk_bytes = self.audio_buffer[start_idx:]
                    if len(chunk_bytes) % 2 != 0:
                        chunk_bytes = chunk_bytes[:-1]
                    
                    audio_int16 = np.frombuffer(chunk_bytes, dtype=np.int16)
                    audio_float32 = audio_int16.astype(np.float32) / 32768.0
                    
                    initial_prompt = self.confirmed_text[-200:] if self.confirmed_text else None
                    
                    kwargs = {
                        "beam_size": self.config.get("beam_size", 5),
                        "word_timestamps": True,
                        "initial_prompt": initial_prompt,
                        "vad_filter": self.config.get("vad_filter", False)
                    }
                    
                    lang = self.config.get("language", "auto")
                    if lang != "auto":
                        kwargs["language"] = lang
                        
                    temp = self.config.get("temperature", 0.0)
                    if temp == 0.0:
                        kwargs["temperature"] = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
                    else:
                        kwargs["temperature"] = temp
                    
                    segments, info = self.model.transcribe(audio_float32, **kwargs)
                    
                    chunk_text = ""
                    chunk_duration = current_audio_time - chunk_start_time
                    
                    for segment in segments:
                        # Update progress UI using the level bar
                        if chunk_duration > 0:
                            pct = (segment.end / chunk_duration)
                            pct = min(1.0, max(0.0, pct))
                            GLib.idle_add(self.level_bar.set_value, pct)
                            
                        if segment.words:
                            for word in segment.words:
                                abs_time = chunk_start_time + word.start
                                if abs_time >= (self.last_transcribed_time - 0.4):
                                    chunk_text += word.word
                        else:
                            chunk_text += segment.text
                            
                    self.confirmed_text += chunk_text
                
            text = self.confirmed_text.strip()
            logging.info(f"Final transcription complete: {len(text)} chars")
            GLib.idle_add(self.on_transcription_done, text)
        except Exception as e:
            logging.error("Final transcription failed", exc_info=True)
            GLib.idle_add(self.on_transcription_error, str(e))

    def on_transcription_error(self, err):
        self.status_icon.show()
        self.status_icon.set_text("❌")
        self.show_error_notification("Error: Transcripción", str(err))
        GLib.timeout_add(700, self.reset_state)

    def parse_punctuation(self, text):
        replacements = {
            "abre paréntesis": "(",
            "cierra paréntesis": ")",
            "abre comillas": "\"",
            "cierra comillas": "\"",
            "punto y coma": ";",
            "dos puntos": ":",
            "nueva línea": "\n",
            "punto y aparte": ".\n",
            "open parenthesis": "(",
            "close parenthesis": ")",
            "open quote": "\"",
            "close quote": "\"",
            "semicolon": ";",
            "colon": ":",
            "new line": "\n",
        }
        for phrase, symbol in replacements.items():
            pattern = re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE)
            text = pattern.sub(symbol, text)
        text = text.replace("( ", "(").replace(" )", ")")
        text = text.replace(" \"", "\"").replace("\" ", "\"")
        return text

    def on_transcription_done(self, text):
        if not text:
            self.reset_state()
            return
            
        self.last_original_text = text
            
        use_llm = False
        if self.next_action == "FINISH_AI":
            use_llm = True
        elif self.next_action == "FINISH_NORMAL":
            use_llm = False
        else:
            use_llm = self.config.get("llm_enabled", False)
            
        if use_llm and self.config.get("api_key", "").strip():
            self.state = "CLEANING"
            self.processing_start_time = time.time()
            self.status_icon.set_text("✨")
            
            ctx = self.level_bar.get_style_context()
            ctx.remove_class("transcribing")
            ctx.add_class("cleaning")
            self.level_bar.set_value(1.0)
            
            self.update_tray_status(self.i18n.t("cleaning"))
            threading.Thread(target=self.clean_text_llm, args=(text,), daemon=True).start()
        else:
            self.finalize_text(text)

    def clean_text_llm(self, text):
        try:
            from google import genai
            from google.genai import types
            
            char_count = len(text)
            default_timeout = int(max(120.0, (char_count / 1000.0) * 120.0) * 1000)
            timeout_ms = int(self.config.get("llm_timeout", 120)) * 1000
            if timeout_ms < default_timeout:
                timeout_ms = default_timeout
            
            client = genai.Client(
                api_key=self.config["api_key"].strip(),
                http_options={'timeout': timeout_ms}
            )
            
            default_base_prompt = (
                "You are a real-time voice dictation assistant.\n"
                "Your objective is to clean up the following voice-dictated text, correcting obvious speech recognition errors and punctuation, while keeping it as faithful to the original as possible.\n"
                "If the text includes verbal formatting instructions (e.g. 'open parenthesis', 'new line', 'comma', 'period'), apply them.\n"
                "Use capitalization when appropriate and correct homophones based on context to make sense of the text without changing the original words or adding extra text.\n"
                "CRITICAL: You MUST reply in the EXACT SAME LANGUAGE as the dictated text. Do not translate it. For example, if the input is in Spanish, output in Spanish.\n"
                "Return ONLY the corrected text, without greetings, explanations or translations."
            )
            base_prompt = self.config.get("base_system_prompt", default_base_prompt)
            prompt_parts = [base_prompt]
            
            # Fetch contextual info from database
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # App Profile System Prompt & Vision
                cursor.execute("SELECT system_prompt, enable_vision FROM app_profiles WHERE app_class = ?", (getattr(self, 'current_app_class', ''),))
                row = cursor.fetchone()
                if row:
                    app_prompt = row[0]
                    enable_vision = bool(row[1])
                    
                    if app_prompt:
                        prompt_parts.append(f"Specific context for this application ({self.current_app_class}): {app_prompt}")
                        
                    if enable_vision:
                        import subprocess
                        import PIL.Image
                        import os
                        
                        shot_path = "/tmp/dictate_vision.png"
                        try:
                            # Leer imagen del portapapeles (Wayland)
                            res = subprocess.run(["wl-paste", "-t", "image/png"], capture_output=True)
                            if res.returncode == 0 and len(res.stdout) > 0:
                                with open(shot_path, "wb") as f:
                                    f.write(res.stdout)
                                
                                my_file = client.files.upload(file=shot_path)
                                prompt_parts.append("Below is a context image (screenshot or image copied to clipboard):")
                                prompt_parts.append(my_file)
                                logging.info("Imagen del portapapeles adjuntada exitosamente al prompt.")
                            else:
                                logging.info("No hay imagen en el portapapeles, omitiendo visión.")
                        except Exception as e:
                            logging.error(f"Error obteniendo imagen del portapapeles: {e}")
                
                # Recent history for context
                cursor.execute("SELECT llm_text, original_text FROM history WHERE app_class = ? ORDER BY id DESC LIMIT 3", (getattr(self, 'current_app_class', ''),))
                history_rows = cursor.fetchall()
                if history_rows:
                    hist_text = "Recent dictation history in this application (only for context reference, DO NOT repeat it):\n"
                    for h_llm, h_orig in reversed(history_rows):
                        ref_text = h_llm if h_llm else h_orig
                        if ref_text:
                            hist_text += f"- {ref_text}\n"
                    prompt_parts.append(hist_text)
                    
                conn.close()
            except Exception as e:
                logging.error(f"Error fetching DB context: {e}")
                
            prompt_parts.append(f"Text to correct NOW:\n{text}")
            
            gen_config = types.GenerateContentConfig(
                temperature=float(self.config.get("llm_temperature", 0.7))
            )
            if self.config.get("llm_thinking", False):
                gen_config.thinking_config = types.ThinkingConfig(thinking_budget=-1)
                
            response = client.models.generate_content_stream(
                model=self.config.get("model", "gemma-4"),
                contents=prompt_parts,
                config=gen_config
            )
            
            cleaned_text = ""
            for chunk in response:
                if chunk.text:
                    cleaned_text += chunk.text
                    GLib.idle_add(self.update_live_text, cleaned_text)
                    
            if cleaned_text:
                GLib.idle_add(self.finalize_text, cleaned_text.strip())
            else:
                logging.warning("El modelo devolvió una respuesta vacía o fue bloqueada por seguridad.")
                GLib.idle_add(self.finalize_text, text)
        except Exception as e:
            logging.error(f"LLM Error: {e}", exc_info=True)
            self.show_error_notification("Error: Limpieza IA", str(e))
            GLib.idle_add(self.finalize_text, text)

    def finalize_text(self, text):
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            original = getattr(self, 'last_original_text', text)
            llm_text = text if original != text else None
            
            cursor.execute('''
                INSERT INTO history (app_class, window_title, original_text, llm_text)
                VALUES (?, ?, ?, ?)
            ''', (getattr(self, 'current_app_class', 'unknown'), 
                  getattr(self, 'current_window_title', 'unknown'), 
                  original, llm_text))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error guardando en base de datos: {e}")
        
        self.current_text = text
        if self.next_action == "PREVIEW":
            self.show_preview()
        elif self.next_action == "FINISH_NORMAL":
            self.status_icon.set_text("✅")
            GLib.timeout_add(600, self.execute_paste, text, self.config.get("auto_send", False))
        elif self.next_action == "FINISH_AI":
            self.status_icon.set_text("✅")
            GLib.timeout_add(600, self.execute_paste, text, self.config.get("auto_send", False))

    def show_preview(self):
        self.state = "PREVIEW"
        self.window.show_all()
        self.status_icon.hide()
        self.time_label.hide()
        self.level_bar.hide()
        
        self.text_buffer.set_text(self.current_text)
        self.text_view_scroll.show_all()
        self.button_box.show_all()

    def execute_paste(self, text, auto_send):
        suffix = " " if not auto_send else ""
        full_text = text + suffix
        
        self.window.hide()
        
        def do_actual_paste():
            wl_copy_path = shutil.which("wl-copy")
            if wl_copy_path:
                subprocess.run([wl_copy_path], input=full_text, text=True)
                time.sleep(0.05)
                # Ctrl+V
                subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"])
                if auto_send:
                    time.sleep(0.05)
                    # Presionar Enter
                    subprocess.run(["ydotool", "key", "28:1", "28:0"])
            else:
                subprocess.run(["ydotool", "type", full_text])
                if auto_send:
                    time.sleep(0.05)
                    subprocess.run(["ydotool", "key", "28:1", "28:0"])
            self.reset_state()
            return False
            
        GLib.timeout_add(100, do_actual_paste)
        return False

    def execute_copy(self, widget=None):
        wl_copy_path = shutil.which("wl-copy")
        if wl_copy_path:
            subprocess.run([wl_copy_path], input=self.current_text, text=True)
        self.reset_state()
        return False

    def reset_state(self):
        logging.info("Resetting state to IDLE")
        
        # Save position before hiding
        if self.window.get_realized():
            pos = self.window.get_position()
            size = self.window.get_size()
            self.config["window_x"] = pos[0]
            self.config["window_y"] = pos[1]
            self.config["window_width"] = size[0]
            self.config["window_height"] = size[1]
            self.save_config()
            
        self.window.hide()
        self.state = "IDLE"
        self.update_tray_status(self.i18n.t("ready", self.model_size))
        self.export_state()
        return False

if __name__ == "__main__":
    # Check if daemon is already running
    import sys
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(SOCKET_PATH)
        # If it connects, daemon is running. Send 'settings' command to open config.
        if "--settings" in sys.argv or len(sys.argv) == 1:
            s.sendall(b"settings")
        s.close()
        print("OpenDictate is already running. Settings window opened.")
        sys.exit(0)
    except Exception:
        # Not running, start normal
        pass
        
    app = DictationDaemon()
    Gtk.main()

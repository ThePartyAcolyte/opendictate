#!/usr/bin/env python3
"""
Command-Line Interface (CLI) client for OpenDictate.

Dispatches IPC commands (record, pause, cancel, send, toggle flags, open settings/wizard)
to the running background daemon via Unix Domain Socket, with offline fallback window launchers.
"""

import os
import socket
import sys

# Allow running from the install directory or the repo root
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from core.ipc import SOCKET_PATH


def main() -> None:
    """Parse CLI arguments and dispatch command to OpenDictate daemon or open offline windows."""
    if "--record" in sys.argv or "record" in sys.argv:
        cmd = "record"
    elif "--pause" in sys.argv or "pause" in sys.argv:
        cmd = "pause"
    elif "--cancel" in sys.argv or "cancel" in sys.argv:
        cmd = "cancel"
    elif "--send" in sys.argv or "send" in sys.argv:
        cmd = "send"
    elif "--finish-normal" in sys.argv or "finish-normal" in sys.argv:
        cmd = "finish-normal"
    elif "--finish-ai" in sys.argv or "finish-ai" in sys.argv:
        cmd = "finish-ai"
    elif "--toggle-bubble" in sys.argv:
        cmd = "toggle-bubble"
    elif "--toggle-record-send" in sys.argv:
        cmd = "toggle-record-send"
    elif "--cycle-model" in sys.argv:
        cmd = "cycle-model"
    elif "--toggle-ai" in sys.argv:
        cmd = "toggle-ai"
    elif "--toggle-autosend" in sys.argv:
        cmd = "toggle-autosend"
    elif "--toggle-realtime" in sys.argv:
        cmd = "toggle-realtime"
    elif "--settings" in sys.argv or "settings" in sys.argv:
        cmd = "settings"
    elif "--wizard" in sys.argv or "wizard" in sys.argv:
        cmd = "wizard"
    elif "--check-updates" in sys.argv or "check-updates" in sys.argv:
        cmd = "check-updates"
    elif "--update" in sys.argv or "update" in sys.argv:
        cmd = "update-dialog"
    else:
        print("Usage: opendictate [--record|--pause|--cancel|--finish-normal|--finish-ai|--settings|--wizard|--check-updates|--update|--toggle-bubble|--toggle-record-send|--toggle-ai|--toggle-autosend|--toggle-realtime|--cycle-model]")
        sys.exit(0)

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(SOCKET_PATH)
        s.sendall(cmd.encode('utf-8'))
        s.close()
    except Exception as e:
        if cmd == "settings":
            try:
                import gi
                gi.require_version('Gtk', '3.0')
                from gi.repository import Gtk
                from opendictate_config_ui import ConfigWindow
                from core.config import CONFIG_PATH
                db = os.path.expanduser("~/.local/share/opendictate/opendictate.db")
                win = ConfigWindow(db, CONFIG_PATH)
                win.connect("destroy", Gtk.main_quit)
                Gtk.main()
                sys.exit(0)
            except Exception as ex:
                print(f"Error opening settings window: {ex}")
                sys.exit(1)
        elif cmd == "wizard":
            try:
                import gi
                gi.require_version('Gtk', '3.0')
                from gi.repository import Gtk
                from ui.wizard import FirstRunWizard
                from core.config import ConfigManager
                cm = ConfigManager()
                win = FirstRunWizard(cm, on_finish=cm.save_config)
                win.connect("destroy", Gtk.main_quit)
                Gtk.main()
                sys.exit(0)
            except Exception as ex:
                print(f"Error opening wizard window: {ex}")
                sys.exit(1)
        elif cmd in ("check-updates", "update-dialog"):
            try:
                import gi
                gi.require_version('Gtk', '3.0')
                from gi.repository import Gtk
                from core.config import ConfigManager
                from core.updater import check_for_updates
                from ui.update_dialog import show_update_dialog
                cm = ConfigManager()
                cfg = cm.load_config()

                def _on_found(uinfo):
                    win = show_update_dialog(cfg, cm, uinfo)
                    win.connect("destroy", Gtk.main_quit)

                def _on_latest():
                    print("OpenDictate is already up to date.")
                    sys.exit(0)

                def _on_err(err):
                    print(f"Error checking updates: {err}")
                    sys.exit(1)

                check_for_updates(cfg, cm, force=True, on_update_found=_on_found, on_up_to_date=_on_latest, on_error=_on_err)
                Gtk.main()
                sys.exit(0)
            except Exception as ex:
                print(f"Error checking updates offline: {ex}")
                sys.exit(1)
        print(f"Error connecting to daemon: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

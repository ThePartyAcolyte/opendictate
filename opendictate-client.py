#!/usr/bin/env python3
"""
Command-Line Interface (CLI) client for OpenDictate.

Dispatches IPC commands (record, pause, cancel, send, toggle flags, open settings/wizard)
to the running background daemon via Unix Domain Socket, with offline fallback window launchers.
"""

import json
import os
import socket
import subprocess
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
    elif "--set-config" in sys.argv:
        idx = sys.argv.index("--set-config")
        if len(sys.argv) >= idx + 3:
            key = sys.argv[idx + 1]
            val = sys.argv[idx + 2]
            cmd = f"set-config:{key}:{val}"
        else:
            print("Usage: opendictate --set-config <key> <value>")
            sys.exit(1)
    elif "--save-profile" in sys.argv:
        idx = sys.argv.index("--save-profile")
        if len(sys.argv) >= idx + 4:
            app_class = sys.argv[idx + 1]
            prompt = sys.argv[idx + 2]
            vision = sys.argv[idx + 3].lower() in ["true", "1", "yes"]
            payload = json.dumps({"app_class": app_class, "system_prompt": prompt, "enable_vision": vision})
            cmd = f"save-profile:{payload}"
        elif len(sys.argv) >= idx + 2:
            payload = sys.argv[idx + 1]
            cmd = f"save-profile:{payload}"
        else:
            print("Usage: opendictate --save-profile <app_class> <system_prompt> <enable_vision>")
            sys.exit(1)
    elif "--delete-profile" in sys.argv:
        idx = sys.argv.index("--delete-profile")
        if len(sys.argv) >= idx + 2:
            app_class = sys.argv[idx + 1]
            cmd = f"delete-profile:{app_class}"
        else:
            print("Usage: opendictate --delete-profile <app_class>")
            sys.exit(1)
    elif "--set-json" in sys.argv:
        idx = sys.argv.index("--set-json")
        if len(sys.argv) >= idx + 2:
            json_str = sys.argv[idx + 1]
            cmd = f"set-json:{json_str}"
        else:
            print("Usage: opendictate --set-json '<json>'")
            sys.exit(1)
    elif "--tui" in sys.argv or "tui" in sys.argv:
        try:
            from ui.settings_tui import run_tui
            run_tui()
            sys.exit(0)
        except Exception as e:
            print(f"Error launching TUI settings: {e}. Falling back to GTK/socket...")
            cmd = "settings"
    elif "--settings" in sys.argv or "settings" in sys.argv or "--settings-gtk" in sys.argv:
        cmd = "settings"
    elif "--wizard-tui" in sys.argv:
        try:
            from ui.wizard_tui import run_wizard
            run_wizard()
            sys.exit(0)
        except Exception as e:
            print(f"Error launching TUI wizard: {e}. Falling back to GTK/socket...")
            cmd = "wizard"
    elif "--wizard" in sys.argv or "wizard" in sys.argv or "--wizard-gtk" in sys.argv:
        cmd = "wizard"
    elif "--toggle-autostart" in sys.argv:
        autostart_dir = os.path.expanduser("~/.config/autostart")
        autostart_path = os.path.join(autostart_dir, "opendictate.desktop")
        if os.path.exists(autostart_path):
            os.remove(autostart_path)
            print("Autostart disabled.")
        else:
            os.makedirs(autostart_dir, exist_ok=True)
            home = os.path.expanduser("~")
            content = f"""[Desktop Entry]
Type=Application
Name=OpenDictate
Exec={home}/.local/share/opendictate/.venv/bin/python {home}/.local/share/opendictate/opendictate-daemon.py --force-start
Icon={home}/.local/share/opendictate/img/logo.png
Terminal=false
Categories=Utility;AudioVideo;Accessibility;
X-GNOME-Autostart-enabled=true
"""
            with open(autostart_path, "w") as f:
                f.write(content)
            print("Autostart enabled.")
        sys.exit(0)
    elif "--set-bar-position" in sys.argv:
        idx = sys.argv.index("--set-bar-position")
        if len(sys.argv) >= idx + 2:
            target_pos = sys.argv[idx + 1].lower()
            shell_path = os.path.expanduser("~/.config/omarchy/shell.json")
            if os.path.exists(shell_path) and target_pos in ["left", "center", "right"]:
                try:
                    with open(shell_path, "r") as f:
                        data = json.load(f)
                    bar = data.setdefault("bar", {}).setdefault("layout", {})
                    for section in ["left", "center", "right"]:
                        items = bar.setdefault(section, [])
                        bar[section] = [it for it in items if not (isinstance(it, dict) and it.get("id") == "com.kirulab.opendictate")]
                    if target_pos == "left":
                        bar["left"].append({"id": "com.kirulab.opendictate"})
                    elif target_pos == "center":
                        bar["center"].append({"id": "com.kirulab.opendictate"})
                    else:
                        bar["right"].insert(0, {"id": "com.kirulab.opendictate"})
                    with open(shell_path, "w") as f:
                        json.dump(data, f, indent=2)
                    print(f"Widget moved to '{target_pos}' in shell.json.")
                    subprocess.run(["omarchy-shell", "shell", "rescanPlugins"], capture_output=True)
                except Exception as e:
                    print(f"Error updating shell.json: {e}")
            sys.exit(0)
    elif "--check-updates" in sys.argv or "check-updates" in sys.argv:
        cmd = "check-updates"
    elif "--update" in sys.argv or "update" in sys.argv:
        cmd = "update-dialog"
    else:
        print("Usage: opendictate [--record|--pause|--cancel|--send|--finish-normal|--finish-ai|--settings|--settings-gtk|--wizard|--wizard-gtk|--check-updates|--update|--toggle-bubble|--toggle-record-send|--toggle-ai|--toggle-autosend|--toggle-realtime|--cycle-model]")
        sys.exit(0)

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(SOCKET_PATH)
        s.sendall(cmd.encode('utf-8'))
        s.close()
    except Exception as e:
        if cmd == "settings":
            try:
                from ui.settings_tui import run_tui
                run_tui()
                sys.exit(0)
            except Exception:
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
                from ui.wizard_tui import run_wizard
                run_wizard()
                sys.exit(0)
            except Exception:
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

#!/usr/bin/env python3
"""
Standalone launcher for the OpenDictate First-Run Onboarding & Setup Wizard.
Used for testing and visual debugging.
"""

import os
import sys

# Auto re-exec in virtual environment if available
venv_python = os.path.expanduser("~/.local/share/opendictate/.venv/bin/python")
if os.path.exists(venv_python) and sys.executable != venv_python and "VIRTUAL_ENV" not in os.environ:
    os.execv(venv_python, [venv_python] + sys.argv)

def main():
    if "--gtk" in sys.argv or "--wizard-gtk" in sys.argv or not sys.stdin.isatty():
        try:
            import gi
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gtk
            from core.config import ConfigManager
            from ui.wizard import FirstRunWizard

            config_mgr = ConfigManager()
            wizard = FirstRunWizard(
                config_mgr,
                on_finish=lambda cfg: print("Wizard finished with config:", cfg)
            )
            wizard.connect("destroy", Gtk.main_quit)
            Gtk.main()
            return
        except Exception as e:
            print(f"Error opening GTK wizard: {e}. Falling back to TUI...")

    from ui.wizard_tui import run_wizard
    run_wizard()


if __name__ == "__main__":
    main()


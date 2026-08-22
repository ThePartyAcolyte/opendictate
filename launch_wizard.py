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

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from core.config import ConfigManager
from ui.wizard import FirstRunWizard

def main():
    config_mgr = ConfigManager()
    wizard = FirstRunWizard(
        config_mgr,
        on_finish=lambda cfg: print("Wizard finished with config:", cfg)
    )
    wizard.connect("destroy", Gtk.main_quit)
    Gtk.main()

if __name__ == "__main__":
    main()

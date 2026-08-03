"""
Window and application context detection utility for OpenDictate.

Resolves active application window class name and window title using AT-SPI (pyatspi)
or system environment fallbacks.
"""

import logging
import shutil
import subprocess
from typing import Tuple


def get_active_window_info() -> Tuple[str, str]:
    """Retrieve active window class name and window title.

    Returns:
        Tuple of (app_class, window_title).
    """
    try:
        import pyatspi
        desktop = pyatspi.Registry.getDesktop(0)
        for app in desktop:
            if not app:
                continue
            for window in app:
                if not window:
                    continue
                state = window.getState()
                if state.contains(pyatspi.STATE_ACTIVE):
                    return app.name or "unknown", window.name or "unknown"
        return "unknown", "unknown"
    except ImportError:
        logging.warning("pyatspi is not installed. Install via: sudo apt install python3-pyatspi")
        return "unknown", "unknown"
    except Exception as e:
        logging.error(f"Error fetching active window info: {e}")
        return "unknown", "unknown"


def restore_window_focus(app_class: str, window_title: str) -> bool:
    """Attempt to restore desktop window focus to specified app class or title.

    Args:
        app_class: Application window class name.
        window_title: Application window title.

    Returns:
        True if focus restoration succeeded, False otherwise.
    """
    if not app_class and not window_title:
        return False

    # Attempt 1: wmctrl by title
    wmctrl_path = shutil.which("wmctrl")
    if wmctrl_path and window_title and window_title != "unknown":
        try:
            res = subprocess.run([wmctrl_path, "-a", window_title], capture_output=True, timeout=1.0)
            if res.returncode == 0:
                logging.info(f"Restored window focus via wmctrl: '{window_title}'")
                return True
        except Exception as e:
            logging.debug(f"wmctrl window focus failed: {e}")

    # Attempt 2: xdotool search & activate
    xdotool_path = shutil.which("xdotool")
    if xdotool_path:
        if window_title and window_title != "unknown":
            try:
                res = subprocess.run(
                    [xdotool_path, "search", "--onlyvisible", "--name", window_title, "windowactivate"],
                    capture_output=True, timeout=1.0
                )
                if res.returncode == 0:
                    logging.info(f"Restored window focus via xdotool title search: '{window_title}'")
                    return True
            except Exception as e:
                logging.debug(f"xdotool title focus failed: {e}")

        if app_class and app_class != "unknown":
            try:
                res = subprocess.run(
                    [xdotool_path, "search", "--onlyvisible", "--class", app_class, "windowactivate"],
                    capture_output=True, timeout=1.0
                )
                if res.returncode == 0:
                    logging.info(f"Restored window focus via xdotool class search: '{app_class}'")
                    return True
            except Exception as e:
                logging.debug(f"xdotool class focus failed: {e}")

    # Attempt 3: pyatspi focus component fallback
    try:
        import pyatspi
        desktop = pyatspi.Registry.getDesktop(0)
        for app in desktop:
            if not app:
                continue
            if app_class and app_class != "unknown" and app.name != app_class:
                continue
            for window in app:
                if not window:
                    continue
                if window_title and window_title != "unknown" and window.name == window_title:
                    component = window.queryComponent()
                    if component and hasattr(component, "grabFocus"):
                        component.grabFocus()
                        logging.info(f"Restored window focus via pyatspi Component: '{window.name}'")
                        return True
    except Exception as e:
        logging.debug(f"pyatspi focus restoration failed: {e}")

    logging.warning(f"Could not restore window focus for class '{app_class}', title '{window_title}'")
    return False


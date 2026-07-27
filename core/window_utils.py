"""
Window and application context detection utility for OpenDictate.

Resolves active application window class name and window title using AT-SPI (pyatspi)
or system environment fallbacks.
"""

import logging
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

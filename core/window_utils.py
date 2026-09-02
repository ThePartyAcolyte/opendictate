"""
Window and application context detection utility for OpenDictate.

Resolves active application window class name and window title using AT-SPI (pyatspi)
or system environment fallbacks.
"""

import json
import logging
import shutil
import subprocess
from typing import Tuple, Optional


def get_active_window_info() -> Tuple[str, str, str]:
    """Retrieve active window class name, window title, and window address.

    Returns:
        Tuple of (app_class, window_title, window_address).
    """
    # Attempt 1: Native Hyprland activewindow & focusHistoryID fallback
    hyprctl_path = shutil.which("hyprctl")
    if hyprctl_path:
        try:
            res = subprocess.run([hyprctl_path, "activewindow", "-j"], capture_output=True, text=True, timeout=0.5)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                if data and isinstance(data, dict):
                    app_class = data.get("class", "unknown")
                    window_title = data.get("title", "unknown")
                    window_address = data.get("address", "")
                    # If active window is shell/bar or empty, lookup most recent user window from history
                    if app_class in ["unknown", "quickshell", "com.kirulab.opendictate", ""] or not window_address:
                        res_clients = subprocess.run([hyprctl_path, "clients", "-j"], capture_output=True, text=True, timeout=0.5)
                        if res_clients.returncode == 0 and res_clients.stdout.strip():
                            clients = json.loads(res_clients.stdout)
                            if isinstance(clients, list):
                                valid = [c for c in clients if c.get("class") not in ["quickshell", "com.kirulab.opendictate", ""]]
                                if valid:
                                    valid.sort(key=lambda c: c.get("focusHistoryID", 9999))
                                    top = valid[0]
                                    return top.get("class", "unknown"), top.get("title", "unknown"), top.get("address", "")
                    return app_class or "unknown", window_title or "unknown", window_address or ""
        except Exception as e:
            logging.debug(f"hyprctl activewindow detection failed: {e}")

    # Attempt 2: AT-SPI (pyatspi)
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
                    return app.name or "unknown", window.name or "unknown", ""
        return "unknown", "unknown", ""
    except ImportError:
        logging.debug("pyatspi is not installed.")
        return "unknown", "unknown", ""
    except Exception as e:
        logging.error(f"Error fetching active window info: {e}")
        return "unknown", "unknown", ""


def restore_window_focus(app_class: str, window_title: str, window_address: Optional[str] = None) -> bool:
    """Attempt to restore desktop window focus to specified app class, title, or address.

    Args:
        app_class: Application window class name.
        window_title: Application window title.
        window_address: Hyprland/Wayland window memory address.

    Returns:
        True if focus restoration succeeded, False otherwise.
    """
    import os, socket

    if not app_class and not window_title and not window_address:
        return False

    # Attempt 1: Native Hyprland 0.56+ Lua socket dispatcher
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    sock_path = f"{xdg_runtime}/hypr/{sig}/.socket.sock" if sig else None
    if sock_path and os.path.exists(sock_path):
        queries = []
        if window_address and window_address != "unknown":
            queries.append(f'local w = hl.get_window("address:{window_address}"); if w then hl.dispatch(hl.dsp.focus({{ window = w }})) return "ok" end')
        if app_class and app_class != "unknown":
            queries.append(f'local w = hl.get_window("class:{app_class}"); if w then hl.dispatch(hl.dsp.focus({{ window = w }})) return "ok" end')
        for q in queries:
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(0.5)
                s.connect(sock_path)
                s.sendall(f"eval {q}".encode())
                resp = s.recv(1024)
                s.close()
                if resp.startswith(b"ok"):
                    logging.info(f"Restored Hyprland window focus via Lua socket: address='{window_address}', class='{app_class}'")
                    return True
            except Exception as e:
                logging.debug(f"Hyprland Lua socket focus failed: {e}")

    # Attempt 2: hyprctl dispatch fallback
    hyprctl_path = shutil.which("hyprctl")
    if hyprctl_path:
        if window_address and window_address != "unknown":
            try:
                res = subprocess.run([hyprctl_path, "dispatch", "focuswindow", f"address:{window_address}"], capture_output=True, timeout=0.5)
                if res.returncode == 0:
                    logging.info(f"Restored window focus via hyprctl address: '{window_address}'")
                    return True
            except Exception as e:
                logging.debug(f"hyprctl address focus failed: {e}")

        if app_class and app_class != "unknown":
            try:
                res = subprocess.run([hyprctl_path, "dispatch", "focuswindow", f"class:{app_class}"], capture_output=True, timeout=0.5)
                if res.returncode == 0:
                    logging.info(f"Restored window focus via hyprctl class: '{app_class}'")
                    return True
            except Exception as e:
                logging.debug(f"hyprctl class focus failed: {e}")

    # Attempt 3: wmctrl by title
    wmctrl_path = shutil.which("wmctrl")
    if wmctrl_path and window_title and window_title != "unknown":
        try:
            res = subprocess.run([wmctrl_path, "-a", window_title], capture_output=True, timeout=1.0)
            if res.returncode == 0:
                logging.info(f"Restored window focus via wmctrl: '{window_title}'")
                return True
        except Exception as e:
            logging.debug(f"wmctrl window focus failed: {e}")

    # Attempt 4: xdotool search & activate
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

    # Attempt 5: pyatspi focus component fallback
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

    logging.warning(f"Could not restore window focus for class '{app_class}', title '{window_title}', address '{window_address}'")
    return False


def capture_active_window_screenshot(output_path: str = "/tmp/dictate_vision.png") -> bool:
    """Capture a screenshot of the currently focused window silently in the background.

    Uses Hyprland (grim) under Wayland/Hyprland without any dialogs.
    Falls back to clipboard (wl-paste) or silent window capture tools under GNOME/X11.

    Args:
        output_path: Destination path for PNG screenshot.

    Returns:
        True if an image was captured and saved to output_path, False otherwise.
    """
    import os

    # 1. Native Hyprland (Arch / Omarchy) via grim + activewindow coordinates
    hyprctl_path = shutil.which("hyprctl")
    grim_path = shutil.which("grim")
    if hyprctl_path and grim_path:
        try:
            res = subprocess.run([hyprctl_path, "activewindow", "-j"], capture_output=True, text=True, timeout=0.5)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                at = data.get("at")
                size = data.get("size")
                if at and size and len(at) == 2 and len(size) == 2:
                    geom = f"{at[0]},{at[1]} {size[0]}x{size[1]}"
                    res_grim = subprocess.run([grim_path, "-g", geom, output_path], capture_output=True, timeout=1.0)
                    if res_grim.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        logging.info(f"Captured silent Hyprland window screenshot: {geom} -> {output_path}")
                        return True
        except Exception as e:
            logging.debug(f"Hyprland grim capture failed: {e}")

    # 2. GNOME / Ubuntu / Wayland fallback: check clipboard image
    wl_paste_path = shutil.which("wl-paste")
    if wl_paste_path:
        try:
            res = subprocess.run([wl_paste_path, "-t", "image/png"], capture_output=True, timeout=0.5)
            if res.returncode == 0 and len(res.stdout) > 0:
                with open(output_path, "wb") as f:
                    f.write(res.stdout)
                logging.info(f"Captured image from clipboard via wl-paste -> {output_path}")
                return True
        except Exception as e:
            logging.debug(f"wl-paste capture failed: {e}")

    # 3. Maim on X11 / Xdotool
    maim_path = shutil.which("maim")
    xdotool_path = shutil.which("xdotool")
    if maim_path and xdotool_path:
        try:
            res_win = subprocess.run([xdotool_path, "getactivewindow"], capture_output=True, text=True, timeout=0.5)
            if res_win.returncode == 0 and res_win.stdout.strip():
                win_id = res_win.stdout.strip()
                res_maim = subprocess.run([maim_path, "-i", win_id, output_path], capture_output=True, timeout=1.0)
                if res_maim.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    logging.info(f"Captured X11 window screenshot via maim -> {output_path}")
                    return True
        except Exception as e:
            logging.debug(f"maim capture failed: {e}")

    return False


def get_open_windows_list() -> list:
    """Retrieve list of currently open application windows with class, title, and friendly name.

    Returns:
        List of dicts: [{"class": "...", "title": "...", "app_name": "..."}]
    """
    seen_classes = set()
    windows = []

    # Attempt 1: Native Hyprland (Arch / Omarchy)
    hyprctl_path = shutil.which("hyprctl")
    if hyprctl_path:
        try:
            res = subprocess.run([hyprctl_path, "clients", "-j"], capture_output=True, text=True, timeout=0.5)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                if isinstance(data, list):
                    for win in data:
                        cls = win.get("class", "").strip()
                        title = win.get("title", "").strip()
                        init_title = win.get("initialTitle", "").strip()
                        if cls and cls not in seen_classes:
                            seen_classes.add(cls)
                            windows.append({
                                "class": cls,
                                "title": title or init_title or cls,
                                "app_name": init_title or cls
                            })
                    if windows:
                        return windows
        except Exception as e:
            logging.debug(f"hyprctl clients listing failed: {e}")

    # Attempt 2: wmctrl on X11 / XWayland
    wmctrl_path = shutil.which("wmctrl")
    if wmctrl_path:
        try:
            res = subprocess.run([wmctrl_path, "-lx"], capture_output=True, text=True, timeout=0.5)
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().splitlines():
                    parts = line.split(None, 4)
                    if len(parts) >= 5:
                        cls_full = parts[2]
                        title = parts[4]
                        cls = cls_full.split(".")[-1] if "." in cls_full else cls_full
                        if cls and cls not in seen_classes:
                            seen_classes.add(cls)
                            windows.append({"class": cls, "title": title, "app_name": cls})
                if windows:
                    return windows
        except Exception as e:
            logging.debug(f"wmctrl listing failed: {e}")

    # Attempt 3: pyatspi (GNOME Wayland)
    try:
        import pyatspi
        desktop = pyatspi.Registry.getDesktop(0)
        for app in desktop:
            if not app or not app.name:
                continue
            if app.name not in seen_classes:
                seen_classes.add(app.name)
                windows.append({"class": app.name, "title": app.name, "app_name": app.name})
    except Exception:
        pass

    return windows



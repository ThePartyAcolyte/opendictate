import urllib.request
import json
import threading
import subprocess
import logging
import time
from typing import Dict, Any

from core.__version__ import __version__

GITHUB_API_URL = "https://api.github.com/repos/ThePartyAcolyte/opendictate/releases/latest"

INTERVALS = {
    "daily": 86400,
    "weekly": 604800,
    "monthly": 2592000
}

def _parse_version(v: str) -> list:
    """Parse semver string into a list of integers for comparison."""
    return [int(x) for x in v.split(".") if x.isdigit()]

def check_for_updates(config: Dict[str, Any], config_manager: Any, force: bool = False) -> None:
    """
    Check for updates asynchronously if configured or forced.
    """
    if not force and not config.get("check_updates", False):
        return

    now = time.time()
    last_check = config.get("last_update_check", 0)
    frequency = config.get("update_frequency", "monthly")
    
    interval = INTERVALS.get(frequency, INTERVALS["monthly"])

    if not force and (now - last_check) < interval:
        return

    def _check() -> None:
        try:
            req = urllib.request.Request(GITHUB_API_URL, headers={"User-Agent": "OpenDictate"})
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    latest_tag = data.get("tag_name", "").lstrip("v")
                    release_url = data.get("html_url", "https://github.com/ThePartyAcolyte/opendictate/releases/latest")
                    
                    if _parse_version(latest_tag) > _parse_version(__version__):
                        logging.info(f"Update available: {latest_tag}")
                        _show_update_notification(latest_tag, release_url)
                    elif force:
                        _show_no_update_notification()
                        
                    # Update timestamp
                    config["last_update_check"] = time.time()
                    config_manager.save_config(config)
        except Exception as e:
            logging.debug(f"Failed to check for updates: {e}")
            if force:
                _show_error_notification()

    threading.Thread(target=_check, daemon=True).start()

def _show_update_notification(new_version: str, url: str) -> None:
    try:
        title = "Actualización de OpenDictate"
        message = f"La versión {new_version} está disponible.\n¿Deseas descargarla?"
        result = subprocess.run([
            "notify-send",
            "-a", "OpenDictate",
            "-A", "download=Descargar",
            "-u", "normal",
            "-i", "software-update-available",
            title, message
        ], capture_output=True, text=True)
        
        if "download" in result.stdout:
            import webbrowser
            webbrowser.open(url)
    except Exception as e:
        logging.error(f"Error showing update notification: {e}")

def _show_no_update_notification() -> None:
    try:
        subprocess.run([
            "notify-send",
            "-a", "OpenDictate",
            "-u", "low",
            "-i", "software-update-available",
            "OpenDictate", "Ya tienes la última versión instalada."
        ])
    except Exception:
        pass

def _show_error_notification() -> None:
    try:
        subprocess.run([
            "notify-send",
            "-a", "OpenDictate",
            "-u", "low",
            "-i", "dialog-error",
            "OpenDictate", "Error al buscar actualizaciones. Verifica tu conexión a internet."
        ])
    except Exception:
        pass

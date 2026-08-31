"""
Software update checking, notification, and management module for OpenDictate.

Queries the GitHub Releases API asynchronously, persists update availability in SQLite,
displays native GTK3 update dialogs, and executes automated updates for user-level installations.
"""

import os
import shutil
import tarfile
import urllib.request
import json
import threading
import subprocess
import logging
import time
from typing import Dict, Any, List, Optional, Callable

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib

from core.__version__ import __version__


GITHUB_LATEST_URL = "https://api.github.com/repos/ThePartyAcolyte/opendictate/releases/latest"
GITHUB_RELEASES_URL = "https://api.github.com/repos/ThePartyAcolyte/opendictate/releases"

INTERVALS = {
    "daily": 86400,
    "weekly": 604800,
    "monthly": 2592000
}


def _parse_version_tuple(v: str) -> tuple[List[int], bool, str]:
    """Parse semantic version string into ((major, minor, patch), is_prerelease, prerelease_tag).

    Args:
        v: Version string (e.g. '1.1.0', '1.2.0-rc1', 'v1.2.0-nightly.20260831').

    Returns:
        Tuple of (nums_list, is_prerelease_bool, prerelease_str).
    """
    clean_v = str(v).strip().lstrip("vV")
    prerelease = ""
    is_prerelease = False
    if "-" in clean_v:
        parts = clean_v.split("-", 1)
        base = parts[0]
        prerelease = parts[1]
        is_prerelease = True
    else:
        base = clean_v
    nums = [int(x) for x in base.split(".") if x.isdigit()]
    while len(nums) < 3:
        nums.append(0)
    return (nums, is_prerelease, prerelease)


def is_version_newer(candidate: str, current: str) -> bool:
    """Compare candidate version against current version according to SemVer rules.

    Args:
        candidate: Available release version string.
        current: Currently installed application version string.

    Returns:
        True if candidate is strictly newer than current version.
    """
    c_nums, c_is_pre, c_pre = _parse_version_tuple(candidate)
    cur_nums, cur_is_pre, cur_pre = _parse_version_tuple(current)

    if c_nums > cur_nums:
        return True
    elif c_nums < cur_nums:
        return False
    else:
        # Identical major.minor.patch base version
        if cur_is_pre and not c_is_pre:
            return True
        if not cur_is_pre and c_is_pre:
            return False
        if cur_is_pre and c_is_pre:
            return c_pre > cur_pre
        return False


def _parse_version(v: str) -> List[int]:
    """Legacy helper for integer version components."""
    nums, _, _ = _parse_version_tuple(v)
    return nums


def is_user_installation() -> bool:
    """Determine whether the currently executing OpenDictate resides in user install path.

    Returns:
        True if running from ~/.local/share/opendictate, False otherwise.
    """
    try:
        user_install_dir = os.path.realpath(os.path.expanduser("~/.local/share/opendictate"))
        current_file_dir = os.path.realpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return current_file_dir == user_install_dir
    except Exception as e:
        logging.debug(f"Error checking user installation path: {e}")
        return False


def check_for_updates(
    config: Dict[str, Any],
    config_manager: Any,
    force: bool = False,
    on_update_found: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_up_to_date: Optional[Callable[[], None]] = None,
    on_error: Optional[Callable[[str], None]] = None
) -> None:
    """Check for new OpenDictate releases asynchronously and handle notifications.

    Args:
        config: Application configuration dictionary.
        config_manager: ConfigManager instance to persist update timestamps and state.
        force: If True, bypasses frequency interval check.
        on_update_found: Optional callback invoked when a new version is detected.
        on_up_to_date: Optional callback invoked when application is up to date (for force check).
        on_error: Optional callback invoked on network or parsing error.
    """
    if not force and not config.get("check_updates", False):
        return

    now = time.time()
    last_check = config.get("last_update_check", 0)
    frequency = config.get("update_frequency", "monthly")
    interval = INTERVALS.get(frequency, INTERVALS["monthly"])

    if not force and (now - last_check) < interval:
        return

    def _check_worker() -> None:
        try:
            channel = config.get("update_channel", "stable")
            api_url = GITHUB_RELEASES_URL if channel == "nightly" else GITHUB_LATEST_URL

            req = urllib.request.Request(api_url, headers={"User-Agent": "OpenDictate"})
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    raw_data = json.loads(response.read().decode('utf-8'))
                    if isinstance(raw_data, list):
                        if not raw_data:
                            if force and on_up_to_date:
                                GLib.idle_add(on_up_to_date)
                            return
                        data = raw_data[0]
                    else:
                        data = raw_data

                    latest_tag = data.get("tag_name", "").lstrip("v")
                    release_url = data.get("html_url", "https://github.com/ThePartyAcolyte/opendictate/releases")
                    release_notes = data.get("body", "")
                    tarball_url = data.get("tarball_url", "")
                    is_prerelease = bool(data.get("prerelease", False) or "-" in latest_tag)
                    
                    update_info = {
                        "version": latest_tag,
                        "url": release_url,
                        "notes": release_notes,
                        "tarball_url": tarball_url,
                        "is_prerelease": is_prerelease,
                        "channel": channel
                    }

                    # Update timestamp
                    config["last_update_check"] = time.time()

                    if is_version_newer(latest_tag, __version__):
                        logging.info(f"OpenDictate update available ({channel}): {latest_tag}")
                        config["available_update_version"] = latest_tag
                        config["available_update_url"] = release_url
                        config["available_update_notes"] = release_notes
                        config_manager.save_config(config)

                        # Check if dismissed
                        dismissed_ver = config.get("update_dismissed_version", "")
                        if force or dismissed_ver != latest_tag:
                            if on_update_found:
                                GLib.idle_add(on_update_found, update_info)
                            else:
                                from ui.update_dialog import show_update_dialog
                                GLib.idle_add(show_update_dialog, config, config_manager, update_info)
                    else:
                        logging.debug("OpenDictate is up to date.")
                        if config.get("available_update_version"):
                            config["available_update_version"] = ""
                            config["available_update_notes"] = ""
                        config_manager.save_config(config)

                        if force and on_up_to_date:
                            GLib.idle_add(on_up_to_date)

        except Exception as e:
            logging.debug(f"Failed to check for updates: {e}")
            if force and on_error:
                GLib.idle_add(on_error, str(e))

    threading.Thread(target=_check_worker, daemon=True).start()


def perform_user_update(
    config: Dict[str, Any],
    update_info: Dict[str, Any],
    on_progress: Callable[[str], None],
    on_complete: Callable[[bool, str], None]
) -> None:
    """Download release tarball, update files in user install path, and refresh dependencies.

    Args:
        config: Application configuration dictionary.
        update_info: Dictionary containing release info including tarball_url or version.
        on_progress: Callback to report human-readable progress status strings.
        on_complete: Callback invoked upon finish with (success_bool, message_str).
    """
    def _update_worker() -> None:
        target_dir = os.path.expanduser("~/.local/share/opendictate")
        temp_dir = "/tmp/opendictate_update"
        tar_path = "/tmp/opendictate_release.tar.gz"

        try:
            on_progress("Descargando release desde GitHub...")
            tarball_url = update_info.get("tarball_url")
            if not tarball_url:
                ver = update_info.get("version", "latest")
                tarball_url = f"https://api.github.com/repos/ThePartyAcolyte/opendictate/tarball/v{ver}"

            req = urllib.request.Request(tarball_url, headers={"User-Agent": "OpenDictate"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(tar_path, "wb") as out_f:
                shutil.copyfileobj(resp, out_f)

            on_progress("Extrayendo archivos de actualización...")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)

            with tarfile.open(tar_path, "r:*") as tar:
                tar.extractall(path=temp_dir)

            # Tarballs from GitHub extract into a root directory like ThePartyAcolyte-opendictate-hash
            extracted_items = os.listdir(temp_dir)
            if not extracted_items:
                raise RuntimeError("El archivo descargado está vacío.")
            
            src_root = os.path.join(temp_dir, extracted_items[0])
            if not os.path.isdir(src_root):
                src_root = temp_dir

            # Verify integrity
            if not os.path.exists(os.path.join(src_root, "opendictate-daemon.py")):
                raise RuntimeError("Estructura de release inválida: falta opendictate-daemon.py")

            on_progress("Actualizando componentes de la aplicación...")
            # Copy root python scripts
            py_files = [
                "opendictate-daemon.py",
                "opendictate-client.py",
                "opendictate_config_ui.py",
                "launch_wizard.py",
                "i18n.py",
                "install.sh",
                "uninstall.sh"
            ]
            for pf in py_files:
                src_pf = os.path.join(src_root, pf)
                if os.path.exists(src_pf):
                    shutil.copy2(src_pf, os.path.join(target_dir, pf))

            # Copy subdirectories (core, ui, i18n, plugins, img)
            subdirs = ["core", "ui", "i18n", "plugins", "img"]
            for sdir in subdirs:
                src_sdir = os.path.join(src_root, sdir)
                dst_sdir = os.path.join(target_dir, sdir)
                if os.path.exists(src_sdir):
                    if os.path.exists(dst_sdir):
                        shutil.rmtree(dst_sdir)
                    shutil.copytree(src_sdir, dst_sdir)

            # Update GNOME Extension if installed
            gnome_ext_target = os.path.expanduser(
                "~/.local/share/gnome-shell/extensions/com.kirulab.opendictate@kirulab.com"
            )
            src_gnome = os.path.join(src_root, "gnome-extension/com.kirulab.opendictate@kirulab.com")
            if os.path.exists(gnome_ext_target) and os.path.exists(src_gnome):
                shutil.copytree(src_gnome, gnome_ext_target, dirs_exist_ok=True)
                subprocess.run(["gnome-extensions", "disable", "com.kirulab.opendictate@kirulab.com"], capture_output=True)
                time.sleep(0.3)
                subprocess.run(["gnome-extensions", "enable", "com.kirulab.opendictate@kirulab.com"], capture_output=True)

            # Fix permissions and shebangs
            venv_python = os.path.join(target_dir, ".venv/bin/python")
            if os.path.exists(venv_python):
                on_progress("Actualizando dependencias de entorno virtual...")
                # Verify or update requirements
                req_file = os.path.join(src_root, "requirements.txt")
                if os.path.exists(req_file):
                    subprocess.run([venv_python, "-m", "pip", "install", "-r", req_file], capture_output=True)

                for pf in ["opendictate-daemon.py", "opendictate-client.py", "opendictate_config_ui.py", "launch_wizard.py"]:
                    target_script = os.path.join(target_dir, pf)
                    if os.path.exists(target_script):
                        try:
                            with open(target_script, "r") as f:
                                lines = f.readlines()
                            if lines:
                                lines[0] = f"#!{venv_python}\n"
                                with open(target_script, "w") as f:
                                    f.writelines(lines)
                        except Exception as e:
                            logging.debug(f"Could not adjust shebang for {pf}: {e}")

            for pf in py_files:
                p = os.path.join(target_dir, pf)
                if os.path.exists(p):
                    os.chmod(p, 0o755)

            # Clean temporary files
            if os.path.exists(tar_path):
                os.remove(tar_path)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

            # Reset update state in config
            config["available_update_version"] = ""
            config["available_update_notes"] = ""
            config["update_dismissed_version"] = ""

            on_complete(True, "OK")

        except Exception as e:
            logging.error(f"Error during user update: {e}", exc_info=True)
            # Cleanup on failure
            if os.path.exists(tar_path):
                try:
                    os.remove(tar_path)
                except Exception:
                    pass
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
            on_complete(False, str(e))

    threading.Thread(target=_update_worker, daemon=True).start()


def restart_opendictate_service() -> None:
    """Terminate existing daemon and restart the updated service in background."""
    try:
        user_install_dir = os.path.expanduser("~/.local/share/opendictate")
        venv_python = os.path.join(user_install_dir, ".venv/bin/python")
        daemon_script = os.path.join(user_install_dir, "opendictate-daemon.py")

        python_bin = venv_python if os.path.exists(venv_python) else "python3"

        # Kill running daemon
        subprocess.run(["pkill", "-9", "-f", "opendictate-daemon.py"], capture_output=True)
        time.sleep(0.8)

        # Remove stale socket
        if os.path.exists("/tmp/opendictate.socket"):
            try:
                os.remove("/tmp/opendictate.socket")
            except Exception:
                pass

        # Spawn new daemon
        env = os.environ.copy()
        subprocess.Popen(
            [python_bin, "-u", daemon_script, "--force-start"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setpgrp,
            env=env
        )
    except Exception as e:
        logging.error(f"Failed to restart OpenDictate daemon: {e}")

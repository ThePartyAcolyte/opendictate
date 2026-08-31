"""
Audio concurrency and microphone hardware arbitration monitor for OpenDictate.

Inspects PipeWire audio graph to detect if third-party applications (e.g. Zoom, Discord,
Google Meet, OBS, Telegram, Audacity) are actively capturing audio from the microphone.
"""

import os
import json
import logging
import subprocess
from typing import Tuple, Optional


# Whitelisted internal system wrappers and daemon streams that should NOT trigger mic release
SYSTEM_STREAM_PATTERNS = [
    "opendictate",
    "arecord",
    "aplay",
    "pipewire alsa",
    "alsa_capture",
    "alsa_playback",
    "easyeffects",
    "speech-dispatcher",
    "libcanberra",
    "gnome-shell",
    "xdg-desktop-portal",
    "dictate_aec_mic"
]


def is_microphone_in_use_by_other_apps(own_pid: Optional[int] = None) -> Tuple[bool, Optional[str]]:
    """Check if another non-OpenDictate application is actively recording from the microphone.

    Args:
        own_pid: Current process PID to ignore. Defaults to current process PID.

    Returns:
        Tuple of (is_in_use, external_app_name).
    """
    target_pid = own_pid or os.getpid()
    try:
        res = subprocess.run(
            ["pw-dump", "Node"],
            capture_output=True,
            text=True,
            timeout=0.6
        )
        if res.returncode != 0:
            return False, None

        nodes = json.loads(res.stdout)
        for n in nodes:
            info = n.get("info", {})
            props = info.get("props", {})
            media_class = props.get("media.class", "")
            state = info.get("state", "")

            # Look for active audio capture streams
            if media_class == "Stream/Input/Audio" and state in ("running", "active"):
                app_pid = props.get("application.process.id")
                app_name = str(
                    props.get("application.name") or
                    props.get("node.name") or
                    props.get("application.process.binary") or
                    ""
                )
                binary = str(props.get("application.process.binary") or "")

                # Skip our own daemon PID
                if app_pid and str(app_pid) == str(target_pid):
                    continue

                full_identity = f"{app_name.lower()} {binary.lower()}"

                # Ignore whitelisted system tools and PipeWire ALSA bridges
                if any(pat in full_identity for pat in SYSTEM_STREAM_PATTERNS):
                    continue

                logging.info(f"Detected genuine external microphone user: {app_name} (PID: {app_pid})")
                return True, app_name or binary or "External Application"

        return False, None
    except Exception as e:
        logging.debug(f"Could not query PipeWire stream concurrency: {e}")
        return False, None

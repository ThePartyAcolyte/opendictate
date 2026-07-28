"""
MPRIS D-Bus media player control module for OpenDictate.

Automatically pauses active media playback (Spotify, Firefox, VLC, etc.) during voice recording
and resumes playback when recording completes.
"""

import logging
from typing import List, Dict, Any

try:
    import dbus
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False


class MediaController:
    """Manages MPRIS D-Bus media player pause and resume operations."""

    def __init__(self) -> None:
        self.paused_players: List[str] = []

    def pause_media(self, config: Dict[str, Any]) -> None:
        """Pause currently playing MPRIS media players if auto_pause_media is enabled.

        Args:
            config: Application configuration dictionary.
        """
        if not config.get("auto_pause_media", True):
            return

        if not HAS_DBUS:
            logging.warning("python-dbus is not installed. Media auto-pause disabled.")
            return

        self.paused_players.clear()
        try:
            bus = dbus.SessionBus()
            for service in bus.list_names():
                if service.startswith('org.mpris.MediaPlayer2.'):
                    try:
                        player = bus.get_object(service, '/org/mpris/MediaPlayer2')
                        props = dbus.Interface(player, 'org.freedesktop.DBus.Properties')
                        status = props.Get('org.mpris.MediaPlayer2.Player', 'PlaybackStatus')
                        if status == 'Playing':
                            iface = dbus.Interface(player, 'org.mpris.MediaPlayer2.Player')
                            iface.Pause()
                            self.paused_players.append(service)
                            logging.info(f"Media automatically paused: {service}")
                    except Exception as e:
                        logging.warning(f"Error pausing MPRIS player {service}: {e}")
        except Exception as e:
            logging.error(f"D-Bus error while pausing media: {e}")

    def resume_media(self) -> None:
        """Resume playback for media players paused during recording."""
        if not HAS_DBUS or not self.paused_players:
            self.paused_players.clear()
            return

        try:
            bus = dbus.SessionBus()
            for service in self.paused_players:
                try:
                    player = bus.get_object(service, '/org/mpris/MediaPlayer2')
                    iface = dbus.Interface(player, 'org.mpris.MediaPlayer2.Player')
                    iface.Play()
                    logging.info(f"Media automatically resumed: {service}")
                except Exception as e:
                    logging.warning(f"Error resuming MPRIS player {service}: {e}")
        except Exception as e:
            logging.error(f"D-Bus error while resuming media: {e}")

        self.paused_players.clear()

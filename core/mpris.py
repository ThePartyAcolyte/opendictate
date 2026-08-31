"""
MPRIS D-Bus media player control and PipeWire/PulseAudio stream muting module for OpenDictate.

Automatically pauses active media playback (Spotify, Firefox, VLC, Stremio, etc.) during voice recording
and mutes any uncooperative active audio streams as a 100% fallback. Resumes and unmutes when recording completes.
"""

import json
import logging
import shutil
import subprocess
from typing import List, Dict, Any, Set

try:
    import dbus
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False


class MediaController:
    """Manages MPRIS D-Bus media player pause/resume and PipeWire/PulseAudio stream muting."""

    def __init__(self) -> None:
        self.paused_players: List[str] = []
        self.muted_stream_ids: Set[int] = set()
        self._has_wpctl = shutil.which("wpctl") is not None
        self._has_pw_dump = shutil.which("pw-dump") is not None
        self._has_pactl = shutil.which("pactl") is not None

    def pause_media(self, config: Dict[str, Any]) -> None:
        """Pause active MPRIS media players and mute remaining audio streams.

        Args:
            config: Application configuration dictionary.
        """
        if not config.get("auto_pause_media", True):
            return

        self.paused_players.clear()
        self.muted_stream_ids.clear()

        # Step 1: Semantic MPRIS2 Pause via D-Bus
        if HAS_DBUS:
            try:
                bus = dbus.SessionBus()
                for service in bus.list_names():
                    if service.startswith('org.mpris.MediaPlayer2'):
                        self._try_pause_mpris_service(bus, str(service))
            except Exception as e:
                logging.error(f"D-Bus error while querying MPRIS services: {e}")
        else:
            logging.warning("python-dbus is not installed. Skipping MPRIS pause.")

        # Step 2: Total Mute Fallback for master audio (PipeWire / PulseAudio)
        self._mute_master_audio()

    def _try_pause_mpris_service(self, bus: Any, service: str) -> None:
        """Attempt to pause a single MPRIS2 service with fallbacks.

        Args:
            bus: D-Bus session bus.
            service: Service name (e.g. 'org.mpris.MediaPlayer2.Stremio').
        """
        try:
            player = bus.get_object(service, '/org/mpris/MediaPlayer2')
            props_iface = dbus.Interface(player, 'org.freedesktop.DBus.Properties')
            player_iface = dbus.Interface(player, 'org.mpris.MediaPlayer2.Player')

            is_playing = False
            try:
                status = str(props_iface.Get('org.mpris.MediaPlayer2.Player', 'PlaybackStatus')).lower()
                is_playing = (status == 'playing')
            except Exception:
                # If PlaybackStatus property fails, check CanPause or service name
                try:
                    can_pause = bool(props_iface.Get('org.mpris.MediaPlayer2.Player', 'CanPause'))
                    is_playing = can_pause
                except Exception:
                    is_playing = False

            if is_playing:
                paused_successfully = False
                try:
                    player_iface.Pause()
                    paused_successfully = True
                except Exception as pause_err:
                    logging.debug(f"Pause() failed on {service}, attempting PlayPause(): {pause_err}")
                    try:
                        player_iface.PlayPause()
                        paused_successfully = True
                    except Exception as pp_err:
                        logging.warning(f"Failed to pause MPRIS player {service}: {pp_err}")

                if paused_successfully:
                    self.paused_players.append(service)
                    logging.info(f"Media automatically paused via MPRIS: {service}")
        except Exception as e:
            logging.debug(f"Could not inspect or control MPRIS service {service}: {e}")

    def _mute_master_audio(self) -> None:
        """Mute the master audio output sink as a reliable fallback."""
        if self._has_wpctl:
            try:
                proc = subprocess.run(
                    ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=1
                )
                if proc.returncode == 0:
                    if "[MUTED]" not in proc.stdout:
                        subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"], timeout=1)
                        self.master_muted = True
                        logging.info("Master audio sink muted as recording fallback.")
                return
            except Exception as e:
                logging.debug(f"Error muting master sink via wpctl: {e}")

        if self._has_pactl:
            try:
                subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"], timeout=1)
                self.master_muted = True
                logging.info("Master audio sink muted via pactl.")
            except Exception as e:
                logging.debug(f"Error muting sink via pactl: {e}")

    def _unmute_master_audio(self) -> None:
        """Unmute the master audio output sink if muted by OpenDictate."""
        if getattr(self, 'master_muted', False):
            if self._has_wpctl:
                try:
                    subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], timeout=1)
                    logging.info("Master audio sink unmuted.")
                except Exception as e:
                    logging.warning(f"Error unmuting master sink via wpctl: {e}")
            elif self._has_pactl:
                try:
                    subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"], timeout=1)
                    logging.info("Master audio sink unmuted via pactl.")
                except Exception as e:
                    logging.warning(f"Error unmuting master sink via pactl: {e}")
            self.master_muted = False

    def resume_media(self) -> None:
        """Resume playback for media players and restore master audio."""
        # Step 1: Unmute master sink
        self._unmute_master_audio()

        # Step 2: Resume MPRIS players
        if HAS_DBUS and self.paused_players:
            try:
                bus = dbus.SessionBus()
                for service in self.paused_players:
                    try:
                        player = bus.get_object(service, '/org/mpris/MediaPlayer2')
                        player_iface = dbus.Interface(player, 'org.mpris.MediaPlayer2.Player')
                        try:
                            player_iface.Play()
                        except Exception:
                            player_iface.PlayPause()
                        logging.info(f"Media automatically resumed: {service}")
                    except Exception as e:
                        logging.warning(f"Error resuming MPRIS player {service}: {e}")
            except Exception as e:
                logging.error(f"D-Bus error while resuming media: {e}")

        self.paused_players.clear()


"""
Audio recording and PCM signal stream processing module for OpenDictate.

Manages ALSA recording process (arecord), RMS audio level normalization,
and raw 16kHz 16-bit mono PCM buffer streaming.
"""

import math
import signal
import struct
import subprocess
import logging
from typing import Optional, Callable, Any

AUDIO_FILE_PCM = "/tmp/dictate_recording.wav.pcm"


class AudioRecorder:
    """Handles audio capture sub-process and PCM buffer operations."""

    def __init__(self) -> None:
        self.record_proc: Optional[subprocess.Popen] = None
        self.audio_file_handle: Optional[Any] = None
        self.audio_buffer = bytearray()
        self.audio_level: float = 0.0

    def start_recording(self, device: Optional[str] = None) -> None:
        """Spawn the ALSA arecord process and open local PCM dump file.

        Args:
            device: Optional ALSA/Pulse device name (e.g. 'default' or echo-cancel node).
        """
        self.audio_buffer.clear()
        self.audio_level = 0.0

        cmd = ["arecord", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", "16000"]
        if device and device != "default":
            cmd.extend(["-D", device])

        self.record_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        self.audio_file_handle = open(AUDIO_FILE_PCM, "wb")

    def process_stream_chunk(
        self,
        chunk_size: int = 1024,
        is_paused: bool = False,
        on_level_update: Optional[Callable[[float], None]] = None
    ) -> bool:
        """Read a single chunk from the recording process output.

        Args:
            chunk_size: Bytes to read from stdout stream (default 1024).
            is_paused: If True, read and discard stream data without storing it.
            on_level_update: Optional callback to notify calculated audio level (0.0 to 1.0).

        Returns:
            True if data was successfully read, False if stream closed or process ended.
        """
        if not self.record_proc or not self.record_proc.stdout:
            return False

        data = self.record_proc.stdout.read(chunk_size)
        if not data:
            return False

        if is_paused:
            self.audio_level = 0.0
            if on_level_update:
                on_level_update(0.0)
            return True

        if self.audio_file_handle and not self.audio_file_handle.closed:
            self.audio_file_handle.write(data)

        self.audio_buffer.extend(data)

        if len(data) == chunk_size:
            try:
                samples = struct.unpack(f"<{chunk_size // 2}h", data)
                sum_sq = sum(s * s for s in samples)
                rms = math.sqrt(sum_sq / (chunk_size // 2))
                norm = min(1.0, rms / 4000.0)
                self.audio_level = norm
                if on_level_update:
                    on_level_update(norm)
            except Exception:
                pass

        return True

    def stop_recording(self) -> bytes:
        """Terminate the arecord process group safely, drain remaining pipe buffer, and close file handles.

        Returns:
            Trailing PCM audio bytes drained from pipe before process termination.
        """
        trailing_data = b""
        if self.record_proc:
            proc = self.record_proc
            self.record_proc = None
            try:
                # Drain any remaining buffered data non-blocking from stdout
                if proc.stdout:
                    try:
                        import fcntl
                        fd = proc.stdout.fileno()
                        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
                        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
                        while True:
                            chunk = proc.stdout.read(4096)
                            if not chunk:
                                break
                            trailing_data += chunk
                    except Exception:
                        pass

                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=0.3)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass

        if trailing_data:
            self.audio_buffer.extend(trailing_data)
            if self.audio_file_handle and not self.audio_file_handle.closed:
                self.audio_file_handle.write(trailing_data)

        if self.audio_file_handle:
            try:
                self.audio_file_handle.close()
            except Exception:
                pass
            self.audio_file_handle = None

        return trailing_data

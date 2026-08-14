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

    def start_recording(self) -> None:
        """Spawn the ALSA arecord process and open local PCM dump file."""
        self.audio_buffer.clear()
        self.audio_level = 0.0

        self.record_proc = subprocess.Popen(
            ["arecord", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", "16000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
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

    def stop_recording(self) -> None:
        """Terminate the arecord process safely and close file handles."""
        if self.record_proc:
            if self.record_proc.poll() is None:
                self.record_proc.send_signal(signal.SIGCONT)
                self.record_proc.terminate()
                try:
                    self.record_proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self.record_proc.kill()
            self.record_proc = None

        if self.audio_file_handle:
            try:
                self.audio_file_handle.close()
            except Exception:
                pass
            self.audio_file_handle = None

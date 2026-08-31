"""
Acoustic Echo Cancellation (AEC), Autocalibration, and Analog Saturation Detection module for OpenDictate.

Manages PipeWire/PulseAudio echo-cancellation configuration, acoustic propagation latency measurement
via chirp correlation, and real-time PCM microphone saturation (clipping) monitoring.
"""

import os
import math
import struct
import subprocess
import tempfile
import time
import logging
from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any, List, Tuple

import numpy as np


@dataclass
class CalibrationResult:
    """Acoustic calibration latency and signal quality result."""
    delay_ms: float
    correlation_peak: float
    is_valid: bool
    message: str


class SaturationDetector:
    """Monitors raw PCM S16_LE audio streams for analog clipping and signal saturation."""

    def __init__(
        self,
        clip_threshold: int = 32650,
        ratio_threshold: float = 0.015,
        recovery_time_sec: float = 1.0,
        on_state_change: Optional[Callable[[str], None]] = None
    ) -> None:
        """Initialize saturation detector.

        Args:
            clip_threshold: Absolute sample amplitude considered clipped (max 32767).
            ratio_threshold: Ratio of clipped samples in a window to trigger CLIPPED state.
            recovery_time_sec: Time in seconds with clean signal required to return to HEALTHY.
            on_state_change: Callback fired with new state ('HEALTHY' or 'CLIPPED').
        """
        self.clip_threshold = clip_threshold
        self.ratio_threshold = ratio_threshold
        self.recovery_time_sec = recovery_time_sec
        self.on_state_change = on_state_change

        self.current_state: str = "HEALTHY"  # "HEALTHY" | "CLIPPED"
        self.last_clipped_time: float = 0.0
        self.current_clip_ratio: float = 0.0

    def process_pcm_chunk(self, chunk_data: bytes) -> str:
        """Analyze a PCM S16_LE chunk for clipped samples.

        Args:
            chunk_data: Raw byte buffer of 16-bit signed integer samples.

        Returns:
            Current health state ('HEALTHY' or 'CLIPPED').
        """
        if not chunk_data or len(chunk_data) < 2:
            return self.current_state

        num_samples = len(chunk_data) // 2
        try:
            samples = struct.unpack(f"<{num_samples}h", chunk_data)
            clipped_count = sum(1 for s in samples if abs(s) >= self.clip_threshold)
            self.current_clip_ratio = clipped_count / num_samples
        except Exception:
            return self.current_state

        now = time.time()
        if self.current_clip_ratio >= self.ratio_threshold:
            self.last_clipped_time = now
            if self.current_state != "CLIPPED":
                self.current_state = "CLIPPED"
                logging.warning(f"Microphone saturation detected (clip ratio: {self.current_clip_ratio:.2%})")
                if self.on_state_change:
                    self.on_state_change("CLIPPED")
        else:
            if self.current_state == "CLIPPED" and (now - self.last_clipped_time >= self.recovery_time_sec):
                self.current_state = "HEALTHY"
                logging.info("Microphone signal normalized to HEALTHY.")
                if self.on_state_change:
                    self.on_state_change("HEALTHY")

        return self.current_state

    def process_chunk(self, chunk_data: bytes) -> bool:
        """Analyze chunk and return True if clipped."""
        self.process_pcm_chunk(chunk_data)
        return self.is_clipped

    @property
    def state(self) -> str:
        """Current state string ('HEALTHY' or 'CLIPPED')."""
        return self.current_state

    @property
    def is_clipped(self) -> bool:
        """True if the microphone is currently saturated."""
        return self.current_state == "CLIPPED"


class AcousticCalibrator:
    """Emits acoustic test chirp and computes room propagation delay via cross-correlation."""

    @staticmethod
    def generate_chirp_signal(
        duration_sec: float = 0.35,
        sample_rate: int = 16000,
        f_start: float = 300.0,
        f_end: float = 3500.0
    ) -> np.ndarray:
        """Synthesize logarithmic frequency chirp numpy array with smooth cosine envelope."""
        num_samples = int(duration_sec * sample_rate)
        t = np.linspace(0, duration_sec, num_samples, endpoint=False)
        k = (f_end / f_start) ** (1.0 / duration_sec)
        phase = 2.0 * np.pi * f_start * ((k ** t - 1.0) / np.log(k))
        envelope = np.sin(np.pi * t / duration_sec)
        return (envelope * np.sin(phase) * 0.75).astype(np.float32)

    @classmethod
    def generate_chirp_wav(
        cls,
        file_path: str,
        duration_sec: float = 0.35,
        sample_rate: int = 16000,
        f_start: float = 300.0,
        f_end: float = 3500.0
    ) -> np.ndarray:
        """Generate a logarithmic frequency chirp WAV file for latency calibration."""
        signal = cls.generate_chirp_signal(duration_sec, sample_rate, f_start, f_end)
        int_samples = (signal * 32767).astype(np.int16)

        import wave
        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(int_samples.tobytes())

        return signal

    @staticmethod
    def measure_latency_cross_correlation(
        reference: np.ndarray,
        captured: np.ndarray,
        sample_rate: int = 16000
    ) -> Tuple[float, float]:
        """Compute propagation latency and peak correlation using sliding window normalization."""
        if len(captured) < len(reference):
            return 0.0, 0.0

        corr = np.correlate(captured, reference, mode="valid")
        ref_energy = float(np.sum(reference ** 2))
        cap_sq = captured ** 2
        win_energy = np.convolve(cap_sq, np.ones(len(reference)), mode="valid")
        norm_corr = np.abs(corr) / np.sqrt(ref_energy * win_energy + 1e-9)

        peak_idx = int(np.argmax(norm_corr))
        peak_val = float(norm_corr[peak_idx])
        delay_ms = (peak_idx / sample_rate) * 1000.0
        return delay_ms, peak_val

    def run_calibration(
        self,
        duration_sec: float = 2.5,
        sample_rate: int = 16000,
        capture_device: Optional[str] = None
    ) -> CalibrationResult:
        """Play test chirp and record microphone to measure propagation latency and signal correlation.

        Returns:
            CalibrationResult with measured delay in ms and validation status.
        """
        temp_dir = tempfile.gettempdir()
        chirp_path = os.path.join(temp_dir, "opendictate_calib_chirp.wav")
        record_path = os.path.join(temp_dir, "opendictate_calib_mic.raw")

        chirp_dur = 0.35
        ref_signal = self.generate_chirp_wav(chirp_path, duration_sec=chirp_dur, sample_rate=sample_rate)

        # Start recording
        record_cmd = ["arecord", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", str(sample_rate)]
        if capture_device and capture_device != "default":
            record_cmd.extend(["-D", capture_device])

        pre_play_delay = 0.15
        try:
            with open(record_path, "wb") as rf:
                rec_proc = subprocess.Popen(record_cmd, stdout=rf, stderr=subprocess.DEVNULL)
                time.sleep(pre_play_delay)  # Brief warm-up

                # Play acoustic test tone
                play_cmd = ["pw-play", chirp_path]
                play_proc = subprocess.Popen(play_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    play_proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    play_proc.kill()

                # Generous listening window to capture high-latency Bluetooth buffers and room acoustics
                time.sleep(1.8)
                rec_proc.terminate()
                rec_proc.wait(timeout=1.0)
        except Exception as e:
            return CalibrationResult(
                delay_ms=0.0,
                correlation_peak=0.0,
                is_valid=False,
                message=f"Calibration error: {e}"
            )
        finally:
            if os.path.exists(chirp_path):
                try: os.remove(chirp_path)
                except Exception: pass

        # Analyze cross-correlation
        try:
            with open(record_path, "rb") as rf:
                raw_bytes = rf.read()
            if os.path.exists(record_path):
                try: os.remove(record_path)
                except Exception: pass

            mic_samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            if len(mic_samples) < len(ref_signal):
                return CalibrationResult(
                    delay_ms=0.0,
                    correlation_peak=0.0,
                    is_valid=False,
                    message="Audio capturado insuficiente para calibración."
                )

            # Compute cross-correlation with sliding window normalization
            raw_delay_ms, peak_val = self.measure_latency_cross_correlation(ref_signal, mic_samples, sample_rate=sample_rate)

            # Subtract pre-play delay
            delay_ms = max(0.0, raw_delay_ms - (pre_play_delay * 1000.0))

            is_valid = peak_val >= 0.15
            msg = f"Latencia: {delay_ms:.1f} ms (Correlación: {peak_val:.2f})"
            if not is_valid:
                msg = f"Baja correlación ({peak_val:.2f}). Asegúrese de que los altavoces se escuchan."

            return CalibrationResult(
                delay_ms=round(delay_ms, 1),
                correlation_peak=round(peak_val, 2),
                is_valid=is_valid,
                message=msg
            )
        except Exception as e:
            return CalibrationResult(
                delay_ms=0.0,
                correlation_peak=0.0,
                is_valid=False,
                message=f"Signal processing error: {e}"
            )


class EchoCancelManager:
    """Manages PipeWire WebRTC AEC source configuration and status."""

    def __init__(self) -> None:
        self.calibrator = AcousticCalibrator()
        self.saturation_detector = SaturationDetector()

    def get_preferred_capture_device(self) -> Optional[str]:
        """Detect and return echo-cancel source if available, or default."""
        try:
            proc = subprocess.run(["pw-dump"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=2)
            if proc.returncode == 0 and proc.stdout:
                import json
                data = json.loads(proc.stdout)
                for obj in data:
                    if obj.get('type') == 'PipeWire:Interface:Node':
                        props = obj.get('info', {}).get('props', {})
                        node_name = props.get('node.name', '')
                        media_class = props.get('media.class', '')
                        if media_class == 'Audio/Source' and ('echo-cancel' in node_name.lower() or 'echocancel' in node_name.lower()):
                            return node_name
        except Exception:
            pass
        return "default"

"""
Voice Activity Detection (VAD) and Dynamic Stream Segmentation module for OpenDictate.

Implements adaptive audio stream chunking using dynamic noise-floor tracking,
energy envelope analysis, silence interval detection, retroactive boundary search,
and energy-valley fallback.
"""

import math
import struct
import logging
from typing import Dict, Any, Optional, List, Tuple


class VADStreamSegmenter:
    """Detects voice activity, tracks speech/silence boundaries, and determines dynamic chunk split points."""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_size: int = 512,
        config: Optional[Dict[str, Any]] = None
    ) -> None:
        """Initialize the stream segmenter with audio and temporal threshold configurations.

        Args:
            sample_rate: Audio sampling frequency in Hz (default 16000).
            frame_size: Number of samples per analysis frame (default 512 = 32ms at 16kHz).
            config: Optional application configuration dictionary.
        """
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.bytes_per_sample = 2  # 16-bit PCM
        self.frame_bytes = self.frame_size * self.bytes_per_sample
        self.frame_duration = self.frame_size / float(self.sample_rate)

        # Configuration parameters with defaults tuned for interactive ASR
        cfg = config or {}
        self.min_duration: float = float(cfg.get("chunk_min_duration", 3.0))
        self.silence_duration: float = float(cfg.get("chunk_silence_duration", 0.85))
        self.max_duration: float = float(cfg.get("chunk_max_duration", 30.0))
        self.fallback_silence_duration: float = float(cfg.get("chunk_fallback_silence_duration", 0.5))
        self.search_window: float = float(cfg.get("chunk_search_window", 6.0))
        self.speech_pad: float = float(cfg.get("chunk_speech_pad", 0.3))
        self.min_energy_threshold: float = float(cfg.get("chunk_vad_energy_threshold", 0.030))

        # Runtime state
        self.reset()

    def reset(self) -> None:
        """Reset segmenter state, frame history, noise floor, and silence tracking."""
        self.frames_history: List[Tuple[float, float, bool]] = []  # (timestamp_sec, rms_energy, is_speech)
        self.silence_spans: List[Tuple[float, float]] = []  # [(start_sec, end_sec)]
        self.current_silence_start: Optional[float] = None
        self.processed_samples: int = 0
        self.leftover_bytes: bytearray = bytearray()
        self.last_speech_time: float = 0.0
        self.noise_floor: Optional[float] = None

    def update_config(self, config: Dict[str, Any]) -> None:
        """Update runtime segmentation parameters from a config dictionary."""
        self.min_duration = float(config.get("chunk_min_duration", self.min_duration))
        self.silence_duration = float(config.get("chunk_silence_duration", self.silence_duration))
        self.max_duration = float(config.get("chunk_max_duration", self.max_duration))
        self.fallback_silence_duration = float(config.get("chunk_fallback_silence_duration", self.fallback_silence_duration))
        self.search_window = float(config.get("chunk_search_window", self.search_window))
        self.speech_pad = float(config.get("chunk_speech_pad", self.speech_pad))
        self.min_energy_threshold = float(config.get("chunk_vad_energy_threshold", self.min_energy_threshold))

    def process_pcm_chunk(self, pcm_bytes: bytes) -> None:
        """Process incoming raw 16-bit 16kHz PCM audio bytes into frames and track voice activity.

        Args:
            pcm_bytes: Raw PCM byte buffer.
        """
        if not pcm_bytes:
            return

        self.leftover_bytes.extend(pcm_bytes)

        while len(self.leftover_bytes) >= self.frame_bytes:
            frame_data = bytes(self.leftover_bytes[:self.frame_bytes])
            del self.leftover_bytes[:self.frame_bytes]

            # Calculate RMS energy for 512 samples
            samples = struct.unpack(f"<{self.frame_size}h", frame_data)
            sum_sq = sum(s * s for s in samples)
            rms = math.sqrt(sum_sq / self.frame_size) / 32768.0  # Normalize to [0.0, 1.0]

            frame_time = (self.processed_samples + self.frame_size) / float(self.sample_rate)
            self.processed_samples += self.frame_size

            # Adaptive noise floor estimation
            if self.noise_floor is None:
                self.noise_floor = rms
            else:
                if rms < self.noise_floor * 1.8:
                    # Normal background noise frame -> adapt quickly
                    self.noise_floor = 0.96 * self.noise_floor + 0.04 * rms
                elif rms > self.noise_floor * 3.0:
                    # Speech frame -> adapt noise floor very slowly upward to track slow acoustic shifts
                    self.noise_floor = 0.999 * self.noise_floor + 0.001 * (rms * 0.15)

            # Clamp noise floor to sane bounds
            self.noise_floor = max(0.001, min(0.06, self.noise_floor))

            # Calculate dynamic speech detection threshold
            dynamic_threshold = max(self.min_energy_threshold, (self.noise_floor * 2.0) + 0.008)
            is_speech = rms >= dynamic_threshold

            if is_speech:
                self.last_speech_time = frame_time
                if self.current_silence_start is not None:
                    # Silence interval ended
                    self.silence_spans.append((self.current_silence_start, frame_time))
                    self.current_silence_start = None
            else:
                if self.current_silence_start is None:
                    # Silence interval started
                    self.current_silence_start = frame_time - self.frame_duration

            self.frames_history.append((frame_time, rms, is_speech))

    def get_trailing_silence_duration(self, current_audio_time: float) -> float:
        """Return the current ongoing silence duration in seconds."""
        if self.current_silence_start is not None:
            return max(0.0, current_audio_time - self.current_silence_start)
        if self.last_speech_time > 0.0:
            return max(0.0, current_audio_time - self.last_speech_time)
        return 0.0

    def find_cut_point(self, current_audio_time: float, last_cut_time: float) -> Optional[float]:
        """Evaluate whether a natural or fallback chunk cut point has been reached.

        Decision sequence:
        1. Ensure elapsed time >= min_duration.
        2. Check for standard silence cut (trailing silence >= silence_duration).
        3. If elapsed time >= max_duration:
           a. Retroactive search for silence span >= fallback_silence_duration within search_window.
           b. Fallback to local minimum RMS energy frame within search_window.

        Args:
            current_audio_time: Total recorded audio duration in seconds.
            last_cut_time: Timestamp of the previous chunk split in seconds.

        Returns:
            Timestamp in seconds for the chunk split point, or None if no cut is warranted.
        """
        elapsed = current_audio_time - last_cut_time

        # 1. Immune window: Do not cut before min_duration
        if elapsed < self.min_duration:
            return None

        # Determine current trailing silence duration
        trailing_silence = 0.0
        if self.current_silence_start is not None:
            trailing_silence = current_audio_time - self.current_silence_start

        # 2. Standard cut condition: elapsed >= min_duration and trailing silence >= silence_duration
        if trailing_silence >= self.silence_duration:
            # Cut at start of silence + speech pad
            cut_point = min(
                current_audio_time,
                max(last_cut_time + self.min_duration, (self.current_silence_start or current_audio_time) + self.speech_pad)
            )
            logging.info(
                f"VAD standard cut triggered at t={cut_point:.2f}s "
                f"(chunk_len={cut_point - last_cut_time:.2f}s, silence={trailing_silence:.2f}s, noise_floor={self.noise_floor:.4f})"
            )
            return cut_point

        # 3. Maximum duration boundary evaluation
        if elapsed >= self.max_duration:
            search_start = max(last_cut_time + self.min_duration, current_audio_time - self.search_window)

            # 3a. Search backwards for any recorded silence span >= fallback_silence_duration
            best_candidate_cut: Optional[float] = None
            best_span_duration: float = 0.0

            # Check completed silence spans within search window
            for start_s, end_s in reversed(self.silence_spans):
                if end_s < search_start:
                    break
                if start_s >= search_start:
                    duration = end_s - start_s
                    if duration >= self.fallback_silence_duration and duration > best_span_duration:
                        best_span_duration = duration
                        best_candidate_cut = start_s + self.speech_pad

            # Also check if current trailing silence qualifies
            if trailing_silence >= self.fallback_silence_duration:
                current_cand = (self.current_silence_start or current_audio_time) + self.speech_pad
                if best_candidate_cut is None or trailing_silence >= best_span_duration:
                    best_candidate_cut = current_cand

            if best_candidate_cut is not None:
                logging.info(
                    f"VAD retroactive fallback cut triggered at t={best_candidate_cut:.2f}s "
                    f"(chunk_len={best_candidate_cut - last_cut_time:.2f}s, silence_found={best_span_duration:.2f}s)"
                )
                return best_candidate_cut

            # 3b. Absolute fallback: Find local minimum RMS energy frame in the search window
            min_energy = float("inf")
            min_energy_time = current_audio_time

            for f_time, f_rms, _ in reversed(self.frames_history):
                if f_time < search_start:
                    break
                if f_rms < min_energy:
                    min_energy = f_rms
                    min_energy_time = f_time

            logging.info(
                f"VAD minimum-energy valley fallback cut triggered at t={min_energy_time:.2f}s "
                f"(chunk_len={min_energy_time - last_cut_time:.2f}s, min_rms={min_energy:.4f})"
            )
            return min_energy_time

        return None

    def advance_cut(self, cut_time: float) -> None:
        """Prune frame history and silence intervals prior to cut_time.

        Args:
            cut_time: Timestamp in seconds where the chunk was split.
        """
        self.frames_history = [f for f in self.frames_history if f[0] >= cut_time]
        self.silence_spans = [s for s in self.silence_spans if s[1] >= cut_time]
        if self.current_silence_start is not None and self.current_silence_start < cut_time:
            self.current_silence_start = cut_time

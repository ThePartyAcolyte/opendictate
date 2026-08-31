"""
Few-Shot Voice Commands and Wake Word module for OpenDictate.

Extracts discriminative acoustic MFCC sequences with sinusoidal liftering and temporal
normalization from 16kHz PCM audio buffers, and performs Cosine Dynamic Time Warping (DTW)
sequence alignment against user-enrolled multi-phrase reference samples with individual
per-phrase detection thresholds and daemon state discrimination (IDLE vs RECORDING/PAUSED).
"""

import os
import json
import time
import math
import uuid
import struct
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Tuple, Any

import numpy as np


class AcousticFeatureExtractor:
    """Computes log-mel filterbank energies, MFCCs, liftering, and normalized acoustic feature sequences."""

    def __init__(
        self,
        sample_rate: int = 16000,
        n_fft: int = 512,
        hop_length: int = 160,
        n_mels: int = 40,
        n_mfcc: int = 13,
        lifter_param: float = 22.0
    ) -> None:
        self.sample_rate = sample_rate
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.n_mels = n_mels
        self.n_mfcc = n_mfcc
        self.lifter_param = lifter_param
        self.mel_basis = self._create_mel_filterbank(sample_rate, n_fft, n_mels)

        # DCT-II basis matrix (dropping DC 0)
        m_idx = np.arange(n_mels) + 0.5
        k_idx = np.arange(1, n_mfcc + 1)
        self.dct_matrix = np.cos((np.pi * np.outer(k_idx, m_idx)) / n_mels).astype(np.float32)

        # Sinusoidal lifter vector
        if lifter_param > 0:
            self.lifter = 1.0 + (lifter_param / 2.0) * np.sin(np.pi * k_idx / lifter_param).astype(np.float32)
        else:
            self.lifter = np.ones(n_mfcc, dtype=np.float32)

    @staticmethod
    def _hz_to_mel(hz: float) -> float:
        return 2595.0 * np.log10(1.0 + hz / 700.0)

    @staticmethod
    def _mel_to_hz(mel: float) -> float:
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

    def _create_mel_filterbank(self, sr: int, n_fft: int, n_mels: int) -> np.ndarray:
        """Construct triangular Mel filterbank matrix spanning 100Hz to Nyquist."""
        low_mel = self._hz_to_mel(100.0)
        high_mel = self._hz_to_mel(sr / 2.0)
        mel_points = np.linspace(low_mel, high_mel, n_mels + 2)
        hz_points = self._mel_to_hz(mel_points)
        bin_points = np.floor((n_fft + 1) * hz_points / sr).astype(int)

        filters = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
        for m in range(1, n_mels + 1):
            f_m_minus = bin_points[m - 1]
            f_m = bin_points[m]
            f_m_plus = bin_points[m + 1]

            if f_m > f_m_minus:
                filters[m - 1, f_m_minus:f_m] = (np.arange(f_m_minus, f_m) - f_m_minus) / (f_m - f_m_minus)
            if f_m_plus > f_m:
                filters[m - 1, f_m:f_m_plus] = (f_m_plus - np.arange(f_m, f_m_plus)) / (f_m_plus - f_m)

        return filters

    def extract_mfcc_sequence(self, audio: Any) -> np.ndarray:
        """Convert 1D audio array into normalized 2D MFCC frame sequence (num_frames, n_mfcc)."""
        if isinstance(audio, (bytes, bytearray)):
            if len(audio) == 0:
                return np.zeros((0, self.n_mfcc), dtype=np.float32)
            audio = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        elif not isinstance(audio, np.ndarray):
            audio = np.array(audio, dtype=np.float32)

        if len(audio) < self.n_fft:
            audio = np.pad(audio, (0, self.n_fft - len(audio)))

        # Pre-emphasis filter
        emphasized = np.append(audio[0], audio[1:] - 0.97 * audio[:-1])

        # Short-Time Fourier Transform (STFT) with Hann window
        window = np.hanning(self.n_fft)
        num_frames = max(1, 1 + (len(emphasized) - self.n_fft) // self.hop_length)
        stft_matrix = np.zeros((self.n_fft // 2 + 1, num_frames), dtype=np.float32)

        for t in range(num_frames):
            start = t * self.hop_length
            end = start + self.n_fft
            if end <= len(emphasized):
                frame = emphasized[start:end] * window
                spectrum = np.fft.rfft(frame, self.n_fft)
                stft_matrix[:, t] = np.abs(spectrum) ** 2

        # Mel Filterbank Energy in dB
        mel_energy = np.dot(self.mel_basis, stft_matrix)
        log_mel = 10.0 * np.log10(np.maximum(mel_energy, 1e-10))

        # Compute MFCCs via DCT-II
        mfcc = np.dot(self.dct_matrix, log_mel)  # Shape: (n_mfcc, num_frames)

        # Apply sinusoidal lifter
        mfcc = mfcc * self.lifter[:, np.newaxis]

        # Temporal Cepstral Mean and Variance Normalization across the utterance
        if num_frames > 1:
            mfcc_mean = np.mean(mfcc, axis=1, keepdims=True)
            mfcc_std = np.std(mfcc, axis=1, keepdims=True) + 1e-6
            mfcc = (mfcc - mfcc_mean) / mfcc_std

        # Frame-level unit normalization for cosine comparison
        frame_norms = np.linalg.norm(mfcc, axis=0, keepdims=True) + 1e-6
        normalized_frames = (mfcc / frame_norms).T  # Shape: (num_frames, n_mfcc)

        return normalized_frames.astype(np.float32)


def trim_silence_vad(
    samples: np.ndarray,
    sample_rate: int = 16000,
    frame_ms: int = 20,
    threshold_rms: float = 0.050,
    margin_ms: int = 80
) -> np.ndarray:
    """Isolate active speech segment by trimming leading and trailing low-energy silence."""
    if len(samples) < 320:
        return samples

    frame_len = int(sample_rate * frame_ms / 1000)
    margin_samples = int(sample_rate * margin_ms / 1000)
    num_frames = len(samples) // frame_len
    if num_frames == 0:
        return samples

    frames = samples[:num_frames * frame_len].reshape((num_frames, frame_len))
    rms_per_frame = np.sqrt(np.mean(frames ** 2, axis=1))

    active_frames = np.where(rms_per_frame >= threshold_rms)[0]
    if len(active_frames) == 0:
        return samples

    start_idx = max(0, active_frames[0] * frame_len - margin_samples)
    end_idx = min(len(samples), (active_frames[-1] + 1) * frame_len + margin_samples)
    return samples[start_idx:end_idx]


def compute_dtw_similarity(seq1: np.ndarray, seq2: np.ndarray) -> float:
    """Compute normalized Cosine Dynamic Time Warping (DTW) similarity between two MFCC sequences."""
    n, m = len(seq1), len(seq2)
    if n == 0 or m == 0:
        return 0.0

    # Ensure unit normalization per frame
    norm1 = np.linalg.norm(seq1, axis=1, keepdims=True) + 1e-6
    norm2 = np.linalg.norm(seq2, axis=1, keepdims=True) + 1e-6
    s1 = seq1 / norm1
    s2 = seq2 / norm2

    # DP matrix: cosine distance D[i, j] = 1 - dot(s1[i], s2[j]) in [0, 2]
    cost = np.full((n + 1, m + 1), np.inf, dtype=np.float32)
    cost[0, 0] = 0.0

    for i in range(1, n + 1):
        v1 = s1[i - 1]
        dists = 1.0 - np.dot(s2, v1)
        for j in range(1, m + 1):
            cost[i, j] = dists[j - 1] + min(cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])

    norm_dist = float(cost[n, m] / (n + m))
    sim = max(0.0, 1.0 - 1.6 * norm_dist)
    return float(sim)


def compute_recommended_threshold(samples: List[np.ndarray]) -> float:
    """Compute recommended DTW threshold based on cross-sample acoustic consistency."""
    if not samples:
        return 0.75
    if len(samples) == 1:
        return 0.72

    similarities = []
    for i in range(len(samples)):
        for j in range(i + 1, len(samples)):
            sim = compute_dtw_similarity(samples[i], samples[j])
            similarities.append(sim)

    if not similarities:
        return 0.75

    mean_sim = float(np.mean(similarities))
    min_sim = float(np.min(similarities))

    # Recommended threshold = slightly below the minimum cross-sample similarity
    recommended = max(0.60, min(0.90, min(min_sim * 0.92, mean_sim * 0.88)))
    return round(recommended, 2)


@dataclass
class PhraseTemplate:
    """Represents a specific trigger phrase under a voice command action."""
    id: str
    name: str
    threshold: float
    samples: List[np.ndarray] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "threshold": self.threshold,
            "samples": [seq.tolist() for seq in self.samples]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PhraseTemplate":
        phrase_id = data.get("id") or str(uuid.uuid4())[:8]
        name = data.get("name", "Default")
        threshold = float(data.get("threshold", 0.75))
        raw_samples = data.get("samples", [])
        samples = [np.array(seq, dtype=np.float32) for seq in raw_samples]
        return cls(id=phrase_id, name=name, threshold=threshold, samples=samples)


class VoiceCommandManager:
    """Manages multi-phrase voice commands, per-phrase thresholds, and state-aware DTW inference."""

    ACTIONS = ["START", "SEND", "PAUSE", "CANCEL"]

    DEFAULT_ACTION_NAMES = {
        "START": "Iniciar",
        "SEND": "Enviar",
        "PAUSE": "Pausar",
        "CANCEL": "Cancelar",
    }

    def __init__(
        self,
        config: Dict[str, Any],
        on_command_detected: Optional[Callable[[str, float], None]] = None,
        template_path: Optional[str] = None
    ) -> None:
        self.config = config
        self.on_command_detected = on_command_detected
        self.storage_path = template_path
        self.extractor = AcousticFeatureExtractor()
        self._is_saturated: bool = False

        # Mapping: action -> List[PhraseTemplate]
        self.phrases_by_action: Dict[str, List[PhraseTemplate]] = {
            action: [] for action in self.ACTIONS
        }

        # Real-time sliding window buffer (approx 1.2s at 16kHz mono = 19200 samples)
        self.window_samples: int = 19200
        self.audio_ring_buffer = np.zeros(self.window_samples, dtype=np.float32)
        self.samples_collected: int = 0
        self.cooldown_until: float = 0.0
        self.cooldown_sec: float = 1.6

        self.load_templates()

    @property
    def templates(self) -> Dict[str, List[np.ndarray]]:
        """Backwards-compatible property returning flat list of samples for first phrase of each action."""
        flat_dict = {}
        for action, phrases in self.phrases_by_action.items():
            if phrases:
                flat_dict[action] = phrases[0].samples
            else:
                flat_dict[action] = []
        return flat_dict

    def get_vad_threshold(self) -> float:
        """Get calibrated speech VAD RMS threshold from config."""
        return float(self.config.get("voice_vad_threshold", 0.075))

    def set_command_callback(self, callback: Callable[[str, float], None]) -> None:
        """Set detection event callback."""
        self.on_command_detected = callback

    def set_saturation_state(self, is_saturated: bool) -> None:
        """Set saturation bypass state."""
        self._is_saturated = is_saturated

    def reset_buffer(self, cooldown: float = 1.5) -> None:
        """Reset sliding window buffer and enforce debounce cooldown."""
        self.audio_ring_buffer.fill(0)
        self.samples_collected = 0
        self.cooldown_until = time.time() + cooldown

    def get_phrases_for_action(self, action: str) -> List[PhraseTemplate]:
        """Get list of phrases registered for a given action."""
        if action not in self.phrases_by_action:
            self.phrases_by_action[action] = []
        if not self.phrases_by_action[action]:
            # Ensure at least one default phrase template exists
            default_name = self.DEFAULT_ACTION_NAMES.get(action, action)
            default_th = float(self.config.get("voice_command_threshold", 0.75))
            self.phrases_by_action[action].append(
                PhraseTemplate(id=f"default_{action.lower()}", name=default_name, threshold=default_th)
            )
        return self.phrases_by_action[action]

    def add_phrase(self, action: str, name: str, threshold: float = 0.75) -> PhraseTemplate:
        """Add a new phrase under an action."""
        if action not in self.phrases_by_action:
            self.phrases_by_action[action] = []
        new_phrase = PhraseTemplate(
            id=str(uuid.uuid4())[:8],
            name=name,
            threshold=threshold,
            samples=[]
        )
        self.phrases_by_action[action].append(new_phrase)
        return new_phrase

    def remove_phrase(self, action: str, phrase_id: str) -> bool:
        """Remove a phrase from an action."""
        if action in self.phrases_by_action:
            phrases = self.phrases_by_action[action]
            self.phrases_by_action[action] = [p for p in phrases if p.id != phrase_id]
            return True
        return False

    def register_sample_pcm(
        self,
        action: str,
        pcm_bytes: bytes,
        phrase_id: Optional[str] = None,
        threshold_rms: Optional[float] = None
    ) -> bool:
        """Enroll a recorded sample with calibrated VAD silence trimming.

        Args:
            action: Action ('START', 'SEND', 'PAUSE', 'CANCEL').
            pcm_bytes: Raw 16kHz 16-bit mono PCM bytes.
            phrase_id: Optional phrase identifier. If None, targets the first phrase of the action.
            threshold_rms: Optional override for speech RMS threshold.

        Returns:
            True if sample was enrolled successfully.
        """
        if action not in self.ACTIONS or len(pcm_bytes) < 1600:
            return False

        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        vad_th = threshold_rms if threshold_rms is not None else self.get_vad_threshold()

        rms = np.sqrt(np.mean(samples ** 2))
        if rms < (vad_th * 0.4):
            logging.warning(f"Rejecting sample for {action}: inaudible audio (RMS: {rms:.4f} vs {vad_th:.4f})")
            return False

        trimmed = trim_silence_vad(samples, sample_rate=16000, threshold_rms=vad_th)
        if len(trimmed) < 2400:
            trimmed = samples

        seq = self.extractor.extract_mfcc_sequence(trimmed)
        if len(seq) < 5:
            return False

        phrases = self.get_phrases_for_action(action)
        target_phrase = None
        if phrase_id:
            for p in phrases:
                if p.id == phrase_id:
                    target_phrase = p
                    break
        if not target_phrase:
            target_phrase = phrases[0]

        target_phrase.samples.append(seq)
        return True

    def clear_templates(self, action: Optional[str] = None, phrase_id: Optional[str] = None) -> None:
        """Clear enrolled templates for a specific phrase or all phrases of an action."""
        if action and action in self.ACTIONS:
            for phrase in self.phrases_by_action.get(action, []):
                if phrase_id is None or phrase.id == phrase_id:
                    phrase.samples.clear()
        else:
            for act in self.ACTIONS:
                for phrase in self.phrases_by_action.get(act, []):
                    phrase.samples.clear()

    def save_templates(self, storage_path: Optional[str] = None) -> None:
        """Persist multi-phrase templates to JSON."""
        target_path = storage_path or self.storage_path
        if not target_path:
            storage_dir = os.path.expanduser("~/.local/share/opendictate")
            os.makedirs(storage_dir, exist_ok=True)
            target_path = os.path.join(storage_dir, "voice_commands.json")

        data = {
            "version": 2,
            "actions": {
                action: [phrase.to_dict() for phrase in phrases]
                for action, phrases in self.phrases_by_action.items()
            }
        }

        try:
            with open(target_path, "w") as f:
                json.dump(data, f)
            logging.info(f"Voice command multi-phrase templates saved to {target_path}")
        except Exception as e:
            logging.error(f"Failed to save voice command templates: {e}")

    def load_templates(self, storage_path: Optional[str] = None) -> None:
        """Load templates with automatic format migration."""
        target_path = storage_path or self.storage_path
        if not target_path:
            target_path = os.path.expanduser("~/.local/share/opendictate/voice_commands.json")

        if not os.path.exists(target_path):
            # Initialize empty defaults
            for action in self.ACTIONS:
                self.get_phrases_for_action(action)
            return

        try:
            with open(target_path, "r") as f:
                raw_data = json.load(f)

            if "version" in raw_data and raw_data["version"] >= 2:
                # Format v2: Multi-phrase structure
                actions_data = raw_data.get("actions", {})
                for action in self.ACTIONS:
                    self.phrases_by_action[action] = [
                        PhraseTemplate.from_dict(pd) for pd in actions_data.get(action, [])
                    ]
            else:
                # Format v1 migration: {"START": [seq1, seq2, ...]}
                for action in self.ACTIONS:
                    samples_raw = raw_data.get(action, [])
                    samples = [np.array(seq, dtype=np.float32) for seq in samples_raw]
                    name = self.DEFAULT_ACTION_NAMES.get(action, action)
                    th = float(self.config.get("voice_command_threshold", 0.75))
                    self.phrases_by_action[action] = [
                        PhraseTemplate(id=f"migrated_{action.lower()}", name=name, threshold=th, samples=samples)
                    ]

            # Ensure all actions have at least one phrase
            for action in self.ACTIONS:
                self.get_phrases_for_action(action)

            logging.info("Voice command multi-phrase templates loaded successfully.")
        except Exception as e:
            logging.warning(f"Could not load voice command templates: {e}")
            for action in self.ACTIONS:
                self.get_phrases_for_action(action)

    def process_stream_chunk(
        self,
        chunk_data: bytes,
        current_daemon_state: str = "IDLE",
        is_saturated: bool = False
    ) -> Optional[Tuple[str, float, float]]:
        """Convenience alias for process_pcm_stream."""
        return self.process_pcm_stream(chunk_data, current_daemon_state, is_saturated)

    def process_pcm_stream(
        self,
        chunk_data: bytes,
        current_daemon_state: str,
        is_saturated: bool = False
    ) -> Optional[Tuple[str, float, float]]:
        """Perform state-discriminated real-time command inference via Cosine DTW with Suffix Matching.

        - In state 'IDLE': strictly evaluates 'START' wake word phrases only.
        - In state 'RECORDING' or 'PAUSED': strictly evaluates 'SEND', 'PAUSE', 'CANCEL' phrases only.

        Args:
            chunk_data: Raw 16kHz S16_LE PCM bytes.
            current_daemon_state: Current daemon state ('IDLE', 'RECORDING', 'PAUSED').
            is_saturated: True if microphone is currently clipped/saturated.

        Returns:
            Tuple of (detected_action, confidence, duration_seconds) or None.
        """
        if not self.config.get("voice_commands_enabled", False):
            return None

        if not chunk_data:
            return None

        samples = np.frombuffer(chunk_data, dtype=np.int16).astype(np.float32) / 32768.0
        n = len(samples)

        # Append to ring buffer
        if n >= self.window_samples:
            self.audio_ring_buffer[:] = samples[-self.window_samples:]
        else:
            self.audio_ring_buffer = np.roll(self.audio_ring_buffer, -n)
            self.audio_ring_buffer[-n:] = samples

        self.samples_collected += n
        if self.samples_collected < 6400:  # Need at least 0.4s of audio
            return None

        now = time.time()
        if now < self.cooldown_until:
            return None

        vad_threshold = self.get_vad_threshold()

        # Energy gate: check max frame energy in recent window
        frame_blocks = self.audio_ring_buffer.reshape(-1, 320)
        frame_rms = np.sqrt(np.mean(frame_blocks ** 2, axis=1))
        noise_floor = float(self.config.get("voice_vad_noise_floor", 0.030))
        vad_threshold = self.get_vad_threshold()
        if np.max(frame_rms) < max(noise_floor * 1.15, vad_threshold * 0.45):
            return None

        # State discrimination:
        # IDLE -> ONLY START
        # RECORDING/PAUSED -> ONLY SEND, PAUSE, CANCEL
        if current_daemon_state == "IDLE":
            target_actions = ["START"]
        elif current_daemon_state in ("RECORDING", "PAUSED"):
            target_actions = ["SEND", "PAUSE", "CANCEL"]
        else:
            return None

        # Check if any target phrase has enrolled samples
        has_any_samples = False
        for act in target_actions:
            for phrase in self.phrases_by_action.get(act, []):
                if phrase.samples:
                    has_any_samples = True
                    break
            if has_any_samples:
                break

        if not has_any_samples:
            return None

        # Extract active speech segment from ring buffer
        trim_th = max(0.015, noise_floor * 1.25)
        active_speech = trim_silence_vad(self.audio_ring_buffer, sample_rate=16000, threshold_rms=trim_th)
        if len(active_speech) < 2400:
            return None

        # Extract MFCC frame sequence from active speech
        live_seq = self.extractor.extract_mfcc_sequence(active_speech)
        if len(live_seq) < 5:
            return None

        best_action = None
        best_phrase_name = None
        best_sim = 0.0
        best_duration = 0.8

        for action in target_actions:
            for phrase in self.phrases_by_action.get(action, []):
                if not phrase.samples:
                    continue

                sims = []
                for ref_seq in phrase.samples:
                    ref_len = len(ref_seq)
                    # Candidate 1: Full active speech sequence
                    len_ratio = len(live_seq) / max(1, ref_len)
                    if 0.55 <= len_ratio <= 1.85:
                        sims.append(compute_dtw_similarity(live_seq, ref_seq))

                    # Candidate 2: Suffix window comparison for commands at end of continuous speech
                    if len(live_seq) > int(ref_len * 1.15):
                        suffix_frames = int(ref_len * 1.30)
                        suffix_seq = live_seq[-suffix_frames:]
                        sims.append(compute_dtw_similarity(suffix_seq, ref_seq))

                phrase_max_sim = max(sims) if sims else 0.0

                # Check if this phrase exceeded its individual calibrated threshold
                if phrase_max_sim >= phrase.threshold and phrase_max_sim > best_sim:
                    best_sim = phrase_max_sim
                    best_action = action
                    best_phrase_name = phrase.name
                    # Estimate duration from template lengths
                    mean_frames = float(np.mean([len(s) for s in phrase.samples]))
                    best_duration = max(0.5, (mean_frames * 160.0) / 16000.0)

        if best_action and best_sim > 0.0:
            self.reset_buffer(cooldown=self.cooldown_sec)
            logging.info(
                f"Voice Command Recognized: {best_action} [Phrase: '{best_phrase_name}'] "
                f"(Confidence: {best_sim:.2f} >= {phrase.threshold:.2f}, Duration: {best_duration:.2f}s, State: {current_daemon_state})"
            )
            if self.on_command_detected:
                try:
                    self.on_command_detected(best_action, best_sim, best_duration)
                except TypeError:
                    self.on_command_detected(best_action, best_sim)
            return best_action, best_sim, best_duration

        return None

    def evaluate_audio_segment(
        self,
        audio_samples: np.ndarray,
        current_daemon_state: str = "RECORDING"
    ) -> Optional[Tuple[str, float, float]]:
        """Directly evaluate an isolated audio slice (e.g. trailing speech before silence) for voice commands.

        Args:
            audio_samples: 1D float32 numpy array of audio samples (16kHz).
            current_daemon_state: Daemon state ('IDLE', 'RECORDING', 'PAUSED').

        Returns:
            Tuple of (detected_action, confidence, duration_seconds) or None.
        """
        if not self.config.get("voice_commands_enabled", False):
            return None

        if audio_samples is None or len(audio_samples) < 2400:
            return None

        noise_floor = float(self.config.get("voice_vad_noise_floor", 0.030))
        trim_th = max(0.015, noise_floor * 1.25)
        active_speech = trim_silence_vad(audio_samples, sample_rate=16000, threshold_rms=trim_th)
        if len(active_speech) < 2400:
            return None

        live_seq = self.extractor.extract_mfcc_sequence(active_speech)
        if len(live_seq) < 5:
            return None

        if current_daemon_state == "IDLE":
            target_actions = ["START"]
        elif current_daemon_state in ("RECORDING", "PAUSED"):
            target_actions = ["SEND", "PAUSE", "CANCEL"]
        else:
            return None

        best_action = None
        best_phrase_name = None
        best_sim = 0.0
        best_duration = 0.8

        for action in target_actions:
            for phrase in self.phrases_by_action.get(action, []):
                if not phrase.samples:
                    continue

                sims = []
                for ref_seq in phrase.samples:
                    ref_len = len(ref_seq)
                    # Candidate 1: Full active speech sequence
                    len_ratio = len(live_seq) / max(1, ref_len)
                    if 0.55 <= len_ratio <= 1.85:
                        sims.append(compute_dtw_similarity(live_seq, ref_seq))

                    # Candidate 2: Suffix window comparison for commands at end of continuous speech
                    if len(live_seq) > int(ref_len * 1.15):
                        suffix_frames = int(ref_len * 1.30)
                        suffix_seq = live_seq[-suffix_frames:]
                        sims.append(compute_dtw_similarity(suffix_seq, ref_seq))

                phrase_max_sim = max(sims) if sims else 0.0

                if phrase_max_sim >= phrase.threshold and phrase_max_sim > best_sim:
                    best_sim = phrase_max_sim
                    best_action = action
                    best_phrase_name = phrase.name
                    mean_frames = float(np.mean([len(s) for s in phrase.samples]))
                    best_duration = max(0.5, (mean_frames * 160.0) / 16000.0)

        if best_action and best_sim > 0.0:
            logging.info(
                f"Tail Voice Command Recognized: {best_action} [Phrase: '{best_phrase_name}'] "
                f"(Confidence: {best_sim:.2f} >= {phrase.threshold:.2f}, Duration: {best_duration:.2f}s)"
            )
            return best_action, best_sim, best_duration

        return None

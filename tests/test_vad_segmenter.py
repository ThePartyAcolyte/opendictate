"""
Unit tests for VADStreamSegmenter dynamic chunking, adaptive noise floor, and boundary search.
"""

import unittest
import struct
import numpy as np
from core.vad import VADStreamSegmenter


def generate_pcm_sine(duration_s: float, freq: float = 440.0, amplitude: float = 0.5, sample_rate: int = 16000) -> bytes:
    """Generate 16-bit mono PCM sine wave audio bytes (speech simulation)."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    samples = (np.sin(2 * np.pi * freq * t) * amplitude * 32767).astype(np.int16)
    return samples.tobytes()


def generate_pcm_noise(duration_s: float, amplitude: float = 0.02, sample_rate: int = 16000) -> bytes:
    """Generate 16-bit mono PCM pseudo-random white noise bytes (ambient mic noise)."""
    num_samples = int(sample_rate * duration_s)
    noise = (np.random.uniform(-amplitude, amplitude, num_samples) * 32767).astype(np.int16)
    return noise.tobytes()


def generate_pcm_silence(duration_s: float, sample_rate: int = 16000) -> bytes:
    """Generate 16-bit mono PCM silence bytes."""
    num_samples = int(sample_rate * duration_s)
    return b"\x00\x00" * num_samples


class TestVADStreamSegmenter(unittest.TestCase):

    def setUp(self):
        self.config = {
            "chunk_min_duration": 3.0,
            "chunk_silence_duration": 0.7,
            "chunk_max_duration": 20.0,
            "chunk_fallback_silence_duration": 0.4,
            "chunk_search_window": 6.0,
            "chunk_vad_energy_threshold": 0.012
        }
        self.segmenter = VADStreamSegmenter(config=self.config)

    def test_standard_silence_cut_after_min_duration(self):
        """Test that silence of 0.7s after min_duration (3.0s) triggers a standard cut."""
        # 4.0s speech + 0.8s silence
        speech = generate_pcm_sine(4.0, amplitude=0.5)
        silence = generate_pcm_silence(0.8)
        total_audio = speech + silence

        self.segmenter.process_pcm_chunk(total_audio)
        total_time = 4.8

        cut_point = self.segmenter.find_cut_point(total_time, last_cut_time=0.0)
        self.assertIsNotNone(cut_point)
        self.assertTrue(3.9 <= cut_point <= 4.8, f"Cut point {cut_point} should be within the silence interval.")

    def test_no_cut_before_min_duration(self):
        """Test that silence occurring before min_duration (3.0s) is ignored."""
        # 1.5s speech + 0.8s silence (total 2.3s < 3.0s)
        speech = generate_pcm_sine(1.5, amplitude=0.5)
        silence = generate_pcm_silence(0.8)
        total_audio = speech + silence

        self.segmenter.process_pcm_chunk(total_audio)
        total_time = 2.3

        cut_point = self.segmenter.find_cut_point(total_time, last_cut_time=0.0)
        self.assertIsNone(cut_point, "Cut point should be None because elapsed time is below min_duration.")

    def test_adaptive_noise_floor_with_mic_ambient_noise(self):
        """Test that VAD detects pauses even with continuous microphone ambient noise (~0.020 RMS)."""
        # Noise floor: 1.0s noise (amp 0.02), then 4.0s speech (amp 0.4) + noise (0.02), then 0.9s pause (noise only)
        noise_init = generate_pcm_noise(1.0, amplitude=0.02)
        speech = generate_pcm_sine(4.0, amplitude=0.4)
        noise_pause = generate_pcm_noise(0.9, amplitude=0.02)
        total_audio = noise_init + speech + noise_pause

        self.segmenter.process_pcm_chunk(total_audio)
        total_time = 5.9

        cut_point = self.segmenter.find_cut_point(total_time, last_cut_time=0.0)
        self.assertIsNotNone(cut_point, "Should trigger cut despite ambient noise due to adaptive threshold.")
        self.assertTrue(4.8 <= cut_point <= 5.9, f"Cut point {cut_point} should be within the pause interval.")

    def test_retroactive_fallback_cut_at_max_duration(self):
        """Test that reaching max_duration (20s) searches for a 0.4s silence in the search window."""
        # Setup: 16s speech + 0.5s silence at t=16..16.5s + 3.5s speech (total 20.0s)
        part1_speech = generate_pcm_sine(16.0, amplitude=0.5)
        silence_span = generate_pcm_silence(0.5)
        part2_speech = generate_pcm_sine(3.5, amplitude=0.5)
        total_audio = part1_speech + silence_span + part2_speech

        chunk_size = 16000 * 2
        for i in range(0, len(total_audio), chunk_size):
            self.segmenter.process_pcm_chunk(total_audio[i:i + chunk_size])

        total_time = 20.0
        cut_point = self.segmenter.find_cut_point(total_time, last_cut_time=0.0)
        self.assertIsNotNone(cut_point)
        self.assertTrue(15.8 <= cut_point <= 16.8, f"Retroactive cut point {cut_point} should be near 16.0s silence.")

    def test_energy_valley_fallback_when_no_silence(self):
        """Test that reaching max_duration (20s) with continuous speech cuts at minimum energy frame."""
        part1 = generate_pcm_sine(17.0, amplitude=0.8)
        dip = generate_pcm_sine(0.4, amplitude=0.05)  # local minimum energy valley
        part2 = generate_pcm_sine(2.6, amplitude=0.8)
        total_audio = part1 + dip + part2

        chunk_size = 16000 * 2
        for i in range(0, len(total_audio), chunk_size):
            self.segmenter.process_pcm_chunk(total_audio[i:i + chunk_size])

        total_time = 20.0
        cut_point = self.segmenter.find_cut_point(total_time, last_cut_time=0.0)
        self.assertIsNotNone(cut_point)
        self.assertTrue(16.5 <= cut_point <= 18.0, f"Valley cut point {cut_point} should be near 17.0s dip.")

    def test_advance_cut_pruning(self):
        """Test that advance_cut properly prunes historical frames and silence spans."""
        speech = generate_pcm_sine(4.0, amplitude=0.5)
        silence = generate_pcm_silence(1.0)
        self.segmenter.process_pcm_chunk(speech + silence)

        cut_point = self.segmenter.find_cut_point(5.0, last_cut_time=0.0)
        self.assertIsNotNone(cut_point)
        self.segmenter.advance_cut(cut_point)

        for frame_time, _, _ in self.segmenter.frames_history:
            self.assertGreaterEqual(frame_time, cut_point - 0.05)


if __name__ == "__main__":
    unittest.main()

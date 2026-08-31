import unittest
import numpy as np
import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock

from core.aec import SaturationDetector, AcousticCalibrator, EchoCancelManager, CalibrationResult
from core.voice_commands import AcousticFeatureExtractor, VoiceCommandManager, compute_dtw_similarity
from core.mpris import MediaController


class TestSaturationDetector(unittest.TestCase):
    def test_healthy_pcm(self):
        state_changes = []
        detector = SaturationDetector(
            clip_threshold=32650,
            ratio_threshold=0.015,
            recovery_time_sec=0.1,
            on_state_change=lambda s: state_changes.append(s)
        )
        
        # Clean sine wave
        t = np.linspace(0, 0.1, 1600, endpoint=False)
        sine = (np.sin(2 * np.pi * 440 * t) * 15000).astype(np.int16)
        pcm = sine.tobytes()

        for _ in range(5):
            is_clipped = detector.process_chunk(pcm)
            self.assertFalse(is_clipped)

        self.assertEqual(detector.state, "HEALTHY")
        self.assertEqual(len(state_changes), 0)

    def test_saturated_pcm_transition(self):
        state_changes = []
        detector = SaturationDetector(
            clip_threshold=32650,
            ratio_threshold=0.015,
            recovery_time_sec=0.05,
            on_state_change=lambda s: state_changes.append(s)
        )

        # Heavily clipped block (90% clipped at 32767)
        clipped_arr = np.full(1600, 32767, dtype=np.int16)
        pcm_clipped = clipped_arr.tobytes()

        is_clipped = detector.process_chunk(pcm_clipped)
        self.assertTrue(is_clipped)
        self.assertEqual(detector.state, "CLIPPED")
        self.assertIn("CLIPPED", state_changes)

        # Feed healthy chunks to test recovery
        import time
        time.sleep(0.06)
        t = np.linspace(0, 0.1, 1600, endpoint=False)
        sine = (np.sin(2 * np.pi * 440 * t) * 5000).astype(np.int16)
        pcm_healthy = sine.tobytes()

        detector.process_chunk(pcm_healthy)
        self.assertEqual(detector.state, "HEALTHY")
        self.assertEqual(state_changes[-1], "HEALTHY")


class TestAcousticFeatureExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = AcousticFeatureExtractor(sample_rate=16000, n_mels=40, n_mfcc=13)

    def test_sequence_shape_and_dtw(self):
        t = np.linspace(0, 0.8, 12800, endpoint=False)
        w1 = (np.sin(2 * np.pi * (400 + 600 * t) * t) * 16000).astype(np.int16).tobytes()
        t2 = np.linspace(0, 0.85, 13600, endpoint=False)
        w1_var = (np.sin(2 * np.pi * (410 + 590 * t2) * t2) * 16000).astype(np.int16).tobytes()
        w2 = (np.sin(2 * np.pi * (1500 - 800 * t) * t) * 16000).astype(np.int16).tobytes()

        seq1 = self.extractor.extract_mfcc_sequence(w1)
        seq1_var = self.extractor.extract_mfcc_sequence(w1_var)
        seq2 = self.extractor.extract_mfcc_sequence(w2)

        self.assertEqual(seq1.shape[1], 13)
        self.assertGreater(seq1.shape[0], 10)

        # Same word variant has high similarity (> 0.85)
        sim_same = compute_dtw_similarity(seq1, seq1_var)
        self.assertGreater(sim_same, 0.85)

        # Different word has low similarity (< 0.50)
        sim_diff = compute_dtw_similarity(seq1, seq2)
        self.assertLess(sim_diff, 0.50)


class TestVoiceCommandManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.template_path = os.path.join(self.temp_dir, "voice_templates.json")
        self.config = {
            "voice_commands_enabled": True,
            "voice_command_threshold": 0.70
        }
        self.manager = VoiceCommandManager(self.config, template_path=self.template_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sample_registration_and_matching(self):
        detected_events = []
        self.manager.set_command_callback(lambda act, score: detected_events.append((act, score)))

        # Create distinct tone sweeps for START and PAUSE
        t = np.linspace(0, 1.0, 16000, endpoint=False)
        start_audio = (np.sin(2 * np.pi * (400 + 600 * t) * t) * 16000).astype(np.int16).tobytes()
        pause_audio = (np.sin(2 * np.pi * (2000 - 800 * t) * t) * 16000).astype(np.int16).tobytes()

        # Enroll 3 samples for START
        for _ in range(3):
            registered = self.manager.register_sample_pcm("START", start_audio)
            self.assertTrue(registered)

        # Enroll 3 samples for PAUSE
        for _ in range(3):
            registered = self.manager.register_sample_pcm("PAUSE", pause_audio)
            self.assertTrue(registered)

        self.assertEqual(len(self.manager.templates["START"]), 3)
        self.assertEqual(len(self.manager.templates["PAUSE"]), 3)

        # Reset cooldown and buffer before testing match
        self.manager.reset_buffer(cooldown=0.0)

        # Feed matching audio in 100ms chunks
        chunk_size = 3200
        for i in range(0, len(start_audio), chunk_size):
            chunk = start_audio[i:i+chunk_size]
            self.manager.process_pcm_stream(chunk, current_daemon_state="IDLE")

        self.assertTrue(len(detected_events) > 0)
        self.assertEqual(detected_events[0][0], "START")
        self.assertGreaterEqual(detected_events[0][1], 0.70)

    def test_state_discrimination(self):
        detected_events = []
        self.manager.set_command_callback(lambda act, score: detected_events.append((act, score)))

        t = np.linspace(0, 1.0, 16000, endpoint=False)
        start_audio = (np.sin(2 * np.pi * (400 + 600 * t) * t) * 16000).astype(np.int16).tobytes()
        send_audio = (np.sin(2 * np.pi * (1800 - 600 * t) * t) * 16000).astype(np.int16).tobytes()

        self.manager.register_sample_pcm("START", start_audio)
        self.manager.register_sample_pcm("SEND", send_audio)

        # In RECORDING state, START should NOT trigger
        self.manager.reset_buffer(cooldown=0.0)
        chunk_size = 3200
        for i in range(0, len(start_audio), chunk_size):
            self.manager.process_pcm_stream(start_audio[i:i+chunk_size], current_daemon_state="RECORDING")
        self.assertEqual(len(detected_events), 0)

        # In RECORDING state, SEND SHOULD trigger
        self.manager.reset_buffer(cooldown=0.0)
        for i in range(0, len(send_audio), chunk_size):
            self.manager.process_pcm_stream(send_audio[i:i+chunk_size], current_daemon_state="RECORDING")
        self.assertTrue(len(detected_events) > 0)
        self.assertEqual(detected_events[0][0], "SEND")

    def test_multi_phrase_and_per_phrase_threshold(self):
        # Add alternative phrase for START
        alt_phrase = self.manager.add_phrase("START", name="OpenDictate", threshold=0.82)
        self.assertEqual(alt_phrase.name, "OpenDictate")
        self.assertEqual(alt_phrase.threshold, 0.82)

        t = np.linspace(0, 1.0, 16000, endpoint=False)
        alt_audio = (np.sin(2 * np.pi * (700 + 300 * t) * t) * 16000).astype(np.int16).tobytes()
        self.manager.register_sample_pcm("START", alt_audio, phrase_id=alt_phrase.id)

        phrases = self.manager.get_phrases_for_action("START")
        self.assertGreaterEqual(len(phrases), 2)

        # Test threshold calculation
        from core.voice_commands import compute_recommended_threshold
        samples = alt_phrase.samples
        sug = compute_recommended_threshold(samples)
        self.assertGreaterEqual(sug, 0.60)

    def test_saturation_resilience(self):
        detected_events = []
        self.manager.set_command_callback(lambda act, score, *args: detected_events.append((act, score)))

        t = np.linspace(0, 1.0, 16000, endpoint=False)
        start_audio = (np.sin(2 * np.pi * (400 + 600 * t) * t) * 16000).astype(np.int16).tobytes()
        for _ in range(3):
            self.manager.register_sample_pcm("START", start_audio)

        # Mark manager as saturated: should still recognize command robustly
        self.manager.set_saturation_state(True)
        self.manager.reset_buffer(cooldown=0.0)

        chunk_size = 3200
        for i in range(0, len(start_audio), chunk_size):
            chunk = start_audio[i:i+chunk_size]
            self.manager.process_stream_chunk(chunk, current_daemon_state="IDLE", is_saturated=True)

        self.assertTrue(len(detected_events) > 0)
        self.assertEqual(detected_events[0][0], "START")

    def test_suffix_matching_during_recording(self):
        detected_events = []
        self.manager.set_command_callback(lambda act, score, *args: detected_events.append((act, score)))

        # Create SEND command template
        t_cmd = np.linspace(0, 0.6, 9600, endpoint=False)
        send_audio = (np.sin(2 * np.pi * (1800 - 800 * t_cmd) * t_cmd) * 16000).astype(np.int16).tobytes()
        self.manager.register_sample_pcm("SEND", send_audio)

        # Preceding speech (0.6s) + SEND command (0.6s) = 1.2s buffer
        t_pre = np.linspace(0, 0.6, 9600, endpoint=False)
        preceding_audio = (np.sin(2 * np.pi * 350 * t_pre) * 12000).astype(np.int16).tobytes()
        continuous_audio = preceding_audio + send_audio

        self.manager.reset_buffer(cooldown=0.0)
        chunk_size = 3200
        for i in range(0, len(continuous_audio), chunk_size):
            self.manager.process_pcm_stream(continuous_audio[i:i+chunk_size], current_daemon_state="RECORDING")

        self.assertTrue(len(detected_events) > 0)
        self.assertEqual(detected_events[0][0], "SEND")

    def test_evaluate_audio_segment_direct(self):
        t_cmd = np.linspace(0, 0.6, 9600, endpoint=False)
        send_audio = (np.sin(2 * np.pi * (1800 - 800 * t_cmd) * t_cmd) * 16000).astype(np.int16).tobytes()
        self.manager.register_sample_pcm("SEND", send_audio)

        samples_float32 = (np.sin(2 * np.pi * (1800 - 800 * t_cmd) * t_cmd) * 0.7).astype(np.float32)
        res = self.manager.evaluate_audio_segment(samples_float32, current_daemon_state="RECORDING")
        self.assertIsNotNone(res)
        action, conf, dur = res
        self.assertEqual(action, "SEND")
        self.assertGreaterEqual(conf, 0.60)
        self.assertGreater(dur, 0.0)


class TestAcousticCalibrator(unittest.TestCase):
    def test_synthetic_delay_measurement(self):
        calibrator = AcousticCalibrator()
        chirp = calibrator.generate_chirp_signal(duration_sec=0.25, sample_rate=16000)

        # Simulate 50ms (800 samples) room acoustic propagation delay + attenuation + noise
        delay_samples = 800
        expected_latency_ms = (delay_samples / 16000) * 1000.0  # 50.0 ms

        captured = np.zeros(len(chirp) + 1600, dtype=np.float32)
        captured[delay_samples:delay_samples + len(chirp)] = chirp * 0.7
        captured += np.random.normal(0, 0.01, size=len(captured)).astype(np.float32)

        measured_latency, peak_corr = calibrator.measure_latency_cross_correlation(chirp, captured, sample_rate=16000)
        self.assertAlmostEqual(measured_latency, expected_latency_ms, delta=1.0)
        self.assertGreater(peak_corr, 0.5)


class TestMprisControllerMasterMuting(unittest.TestCase):
    @patch("subprocess.run")
    def test_mute_master_audio(self, mock_run):
        mpris = MediaController()
        mpris._has_wpctl = True

        def fake_run(cmd, *args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            if "get-volume" in cmd:
                res.stdout = "Volume: 0.80"
            else:
                res.stdout = ""
            return res

        mock_run.side_effect = fake_run

        mpris._mute_master_audio()
        self.assertTrue(mpris.master_muted)

        # Test unmuting
        mpris._unmute_master_audio()
        self.assertFalse(mpris.master_muted)


if __name__ == "__main__":
    unittest.main()


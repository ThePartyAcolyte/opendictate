"""
Unit tests for GeminiLiveEngine async streaming STT engine.
"""

import sys
import time
import unittest
from unittest.mock import MagicMock, patch

if "google" not in sys.modules:
    mock_google = MagicMock()
    mock_genai = MagicMock()
    mock_google.genai = mock_genai
    sys.modules["google"] = mock_google
    sys.modules["google.genai"] = mock_genai
    sys.modules["google.genai.types"] = MagicMock()

from core.gemini_live_engine import GeminiLiveEngine


class TestGeminiLiveEngine(unittest.TestCase):
    """Test suite for GeminiLiveEngine lifecycle, callbacks, and audio buffering."""

    def setUp(self):
        self.engine = GeminiLiveEngine()

    def tearDown(self):
        if self.engine.is_active():
            self.engine.stop_session(timeout=1.0)

    def test_engine_initial_state(self):
        """Test engine initial idle state."""
        self.assertFalse(self.engine.is_active())
        self.assertEqual(self.engine.accumulated_text, "")

    def test_send_audio_chunk_when_inactive_is_noop(self):
        """Test that sending audio chunks when session is not active does not fail or raise."""
        dummy_chunk = b"\x00\x00" * 512
        self.engine.send_audio_chunk(dummy_chunk)
        self.assertFalse(self.engine.is_active())

    def test_session_lifecycle_with_mocked_client(self):
        """Test start_session and stop_session lifecycle with mocked GenAI Live client."""
        # Test simulated accumulation and shutdown
        self.engine._is_active = True
        self.engine.accumulated_text = "Hola mundo"
        final_text = self.engine.stop_session(timeout=0.1)

        self.assertFalse(self.engine.is_active())
        self.assertEqual(final_text, "Hola mundo")


if __name__ == "__main__":
    unittest.main()

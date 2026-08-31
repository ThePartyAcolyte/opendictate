import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure mock google.genai exists if package is not installed in local environment
if "google" not in sys.modules:
    mock_google = MagicMock()
    mock_genai = MagicMock()
    mock_google.genai = mock_genai
    sys.modules["google"] = mock_google
    sys.modules["google.genai"] = mock_genai
    sys.modules["google.genai.types"] = MagicMock()

from core.llm import LLMService, DEFAULT_BASE_PROMPT



class TestLLMService(unittest.TestCase):
    """Test suite for Gemini LLM text post-processing service."""

    def setUp(self):
        self.mock_config_manager = MagicMock()
        self.mock_config_manager.get_app_profile.return_value = (None, False)
        self.mock_config_manager.get_recent_history.return_value = []
        self.service = LLMService(self.mock_config_manager)

    def test_clean_text_returns_original_if_no_api_key(self):
        """Test that missing API key immediately returns original text without network calls."""
        config = {"api_key": ""}
        result = self.service.clean_text("hola mundo", config, "org.gnome.Terminal")
        self.assertEqual(result, "hola mundo")

    def test_clean_text_invokes_genai_and_returns_cleaned_stream(self):
        """Test that configured client streams and aggregates cleaned text chunks."""
        config = {
            "api_key": "test-key-12345",
            "model": "gemma-4-26b-a4b-it",
            "llm_temperature": 0.7,
            "llm_thinking": False
        }

        # Mock chunk streaming response
        chunk1 = MagicMock()
        chunk1.text = "Hola, "
        chunk2 = MagicMock()
        chunk2.text = "mundo."

        mock_client = MagicMock()
        mock_client.models.generate_content_stream.return_value = [chunk1, chunk2]

        with patch("google.genai.Client", return_value=mock_client):
            chunks_received = []
            result = self.service.clean_text(
                "hola mundo",
                config,
                "org.gnome.Terminal",
                on_chunk=lambda c: chunks_received.append(c)
            )

            self.assertEqual(result, "Hola, mundo.")
            self.assertEqual(chunks_received, ["Hola, ", "Hola, mundo."])
            mock_client.models.generate_content_stream.assert_called_once()

    def test_clean_text_handles_llm_exception_gracefully(self):
        """Test that any GenAI API error is logged and returns original uncleaned text."""
        config = {
            "api_key": "test-key-12345",
            "model": "gemma-4-26b-a4b-it"
        }

        mock_client = MagicMock()
        mock_client.models.generate_content_stream.side_effect = RuntimeError("API Quota Exceeded")

        with patch("google.genai.Client", return_value=mock_client):
            result = self.service.clean_text("texto original de prueba", config, "firefox")
            self.assertEqual(result, "texto original de prueba")

    def test_clean_text_includes_app_profile_and_history(self):
        """Test that app-specific prompts and recent dictation history are appended to contents."""
        config = {
            "api_key": "test-key-12345",
            "model": "gemma-4-26b-a4b-it"
        }

        self.mock_config_manager.get_app_profile.return_value = ("Format as SQL query", False)
        self.mock_config_manager.get_recent_history.return_value = [
            ("SELECT * FROM users;", "select all from users")
        ]

        chunk = MagicMock()
        chunk.text = "SELECT * FROM orders;"
        mock_client = MagicMock()
        mock_client.models.generate_content_stream.return_value = [chunk]

        with patch("google.genai.Client", return_value=mock_client):
            result = self.service.clean_text("select all from orders", config, "dbeaver")
            self.assertEqual(result, "SELECT * FROM orders;")

            call_args = mock_client.models.generate_content_stream.call_args[1]
            contents = call_args["contents"]
            self.assertTrue(any("Format as SQL query" in str(p) for p in contents))
            self.assertTrue(any("SELECT * FROM users;" in str(p) for p in contents))

    def test_clean_text_routes_live_model_to_live_api(self):
        """Test that gemini-3.1-flash-live-preview uses async Live API websocket connection."""
        config = {
            "api_key": "test-key-12345",
            "model": "gemini-3.1-flash-live-preview",
            "llm_thinking": True,
            "llm_thinking_level": "minimal"
        }

        # Mock live session return value
        def mock_clean_live(*args, **kwargs):
            on_chunk = kwargs.get("on_chunk")
            if on_chunk:
                on_chunk("Hola ")
                on_chunk("mundo!")
            return "Hola mundo!"

        with patch.object(self.service, "_clean_text_live", side_effect=mock_clean_live) as mock_live:
            chunks = []
            result = self.service.clean_text(
                "hola mundo",
                config,
                "org.gnome.Terminal",
                on_chunk=lambda c: chunks.append(c)
            )
            self.assertEqual(result, "Hola mundo!")
            mock_live.assert_called_once()


if __name__ == "__main__":
    unittest.main()

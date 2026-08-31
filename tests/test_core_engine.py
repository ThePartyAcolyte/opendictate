"""
Unit tests for WhisperEngine fallback resolution and verbal punctuation formatting.
"""

import unittest
from core.engine import WhisperEngine, KNOWN_MODEL_SIZES


class TestWhisperEngine(unittest.TestCase):
    """Test suite for WhisperEngine model management and text helpers."""

    def setUp(self):
        self.engine = WhisperEngine()

    def test_fallback_candidates_order_for_known_models(self):
        """Test fallback candidates prioritizes smaller models before larger models."""
        candidates = WhisperEngine._get_fallback_candidates("medium")
        expected_subset = ["medium.en", "small", "small.en", "base", "base.en", "tiny", "tiny.en", "large-v3", "large-v2", "large-v1", "large"]
        self.assertEqual(candidates, expected_subset)

    def test_fallback_candidates_for_tiny(self):
        """Test fallback candidates for tiny returns tiny.en followed by larger models."""
        candidates = WhisperEngine._get_fallback_candidates("tiny")
        self.assertEqual(candidates[0], "tiny.en")
        self.assertIn("base", candidates)
        self.assertIn("large-v3", candidates)

    def test_fallback_candidates_for_unknown_model(self):
        """Test fallback candidates for arbitrary model name returns KNOWN_MODEL_SIZES."""
        candidates = WhisperEngine._get_fallback_candidates("custom-whisper-model")
        self.assertEqual(candidates, KNOWN_MODEL_SIZES)

    def test_parse_verbal_punctuation_spanish(self):
        """Test replacement of spoken Spanish punctuation commands with symbols."""
        input_text = "hola abre paréntesis esto es una prueba cierra paréntesis dos puntos nueva línea punto y coma"
        output_text = WhisperEngine.parse_verbal_punctuation(input_text)
        expected = "hola (esto es una prueba) : \n ;"
        self.assertEqual(output_text, expected)

    def test_parse_verbal_punctuation_english(self):
        """Test replacement of spoken English punctuation commands with symbols."""
        input_text = "hello open parenthesis test close parenthesis colon new line semicolon"
        output_text = WhisperEngine.parse_verbal_punctuation(input_text)
        expected = "hello (test) : \n ;"
        self.assertEqual(output_text, expected)

    def test_parse_verbal_punctuation_quotes(self):
        """Test replacement of spoken quotes with proper formatting."""
        input_text = "dijo abre comillas hola mundo cierra comillas"
        output_text = WhisperEngine.parse_verbal_punctuation(input_text)
        self.assertEqual(output_text, "dijo\"hola mundo\"")


if __name__ == "__main__":
    unittest.main()

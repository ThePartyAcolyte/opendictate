"""
Speech-to-Text inference engine for OpenDictate using Faster-Whisper.

Supports sliding-window real-time chunk transcription and single-pass full-audio batch decoding.
"""

import re
import time
import logging
import numpy as np
from typing import Dict, Any, Optional, Tuple, Callable


class WhisperEngine:
    """Wrapper class for Faster-Whisper model loading and decoding."""

    def __init__(self) -> None:
        self.model = None
        self.model_size: str = "medium"

    def load_model(self, size: str) -> bool:
        """Load or switch Faster-Whisper model size.

        Args:
            size: Model size name (e.g. tiny, base, small, medium, large-v3).

        Returns:
            True if model loaded successfully, False otherwise.
        """
        logging.info(f"Loading Faster-Whisper model: {size}...")
        try:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(size, device="auto", compute_type="default")
            self.model_size = size
            logging.info(f"Faster-Whisper model '{size}' loaded successfully.")
            return True
        except Exception as e:
            logging.error(f"Error loading Faster-Whisper model '{size}': {e}", exc_info=True)
            return False

    def transcribe_chunk(
        self,
        audio_float32: np.ndarray,
        config: Dict[str, Any],
        initial_prompt: Optional[str] = None
    ) -> Any:
        """Execute Faster-Whisper transcription on a float32 audio array.

        Args:
            audio_float32: Normalized 16kHz float32 audio sample array.
            config: Configuration dictionary.
            initial_prompt: Optional previous text context.

        Returns:
            Tuple of (segments generator, info metadata).
        """
        if not self.model:
            raise RuntimeError("Faster-Whisper model is not loaded.")

        kwargs: Dict[str, Any] = {
            "beam_size": config.get("beam_size", 5),
            "word_timestamps": True,
            "vad_filter": config.get("vad_filter", False)
        }

        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt

        lang = config.get("language", "auto")
        if lang != "auto":
            kwargs["language"] = lang

        temp = config.get("temperature", 0.0)
        if temp == 0.0:
            kwargs["temperature"] = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
        else:
            kwargs["temperature"] = temp

        return self.model.transcribe(audio_float32, **kwargs)

    @staticmethod
    def parse_verbal_punctuation(text: str) -> str:
        """Replace spoken verbal punctuation commands with literal punctuation symbols.

        Args:
            text: Input raw text string.

        Returns:
            Text string with verbal commands converted to punctuation symbols.
        """
        replacements = {
            "abre paréntesis": "(",
            "cierra paréntesis": ")",
            "abre comillas": "\"",
            "cierra comillas": "\"",
            "punto y coma": ";",
            "dos puntos": ":",
            "nueva línea": "\n",
            "punto y aparte": ".\n",
            "open parenthesis": "(",
            "close parenthesis": ")",
            "open quote": "\"",
            "close quote": "\"",
            "semicolon": ";",
            "colon": ":",
            "new line": "\n",
        }
        for phrase, symbol in replacements.items():
            pattern = re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE)
            text = pattern.sub(symbol, text)
        text = text.replace("( ", "(").replace(" )", ")")
        text = text.replace(" \"", "\"").replace("\" ", "\"")
        return text

"""
Speech-to-Text inference engine for OpenDictate using Faster-Whisper.

Supports sliding-window real-time chunk transcription and single-pass full-audio batch decoding.
"""

import re
import time
import logging
import threading
import numpy as np
from typing import Dict, Any, Optional, Tuple, Callable, List

KNOWN_MODEL_SIZES = [
    "large-v3",
    "large-v2",
    "large-v1",
    "large",
    "medium",
    "medium.en",
    "small",
    "small.en",
    "base",
    "base.en",
    "tiny",
    "tiny.en"
]


class WhisperEngine:
    """Wrapper class for Faster-Whisper model loading and decoding."""

    def __init__(self) -> None:
        self.model = None
        self.model_size: str = "medium"
        self.lock = threading.Lock()

    @staticmethod
    def _get_fallback_candidates(requested_size: str) -> List[str]:
        """Generate ordered list of fallback model candidates.

        Prioritizes models smaller than the requested size first, then larger models.

        Args:
            requested_size: Requested model size name.

        Returns:
            List of fallback model size candidate names.
        """
        if requested_size in KNOWN_MODEL_SIZES:
            idx = KNOWN_MODEL_SIZES.index(requested_size)
            candidates = KNOWN_MODEL_SIZES[idx + 1:] + KNOWN_MODEL_SIZES[:idx]
        else:
            candidates = [s for s in KNOWN_MODEL_SIZES if s != requested_size]
        return candidates

    def load_model(self, size: str) -> Tuple[bool, Optional[str], str]:
        """Load Faster-Whisper model with multi-tier fallback resolution.

        Sequence:
        1. Attempt local cached load for requested model (local_files_only=True).
        2. Attempt remote download for requested model (local_files_only=False).
        3. Fallback to any other locally cached Whisper model (local_files_only=True).
        4. Fail gracefully if no models and no internet connection.

        Args:
            size: Model size name (e.g. tiny, base, small, medium, large-v3).

        Returns:
            Tuple of (success: bool, loaded_model_name: Optional[str], status_code: str).
            Status codes: 'loaded_local', 'downloaded', 'fallback_local', 'failed_no_models'.
        """
        logging.info(f"Initiating model loading process for: {size}...")
        try:
            from faster_whisper import WhisperModel
        except ImportError as err:
            logging.error(f"Failed to import faster_whisper: {err}", exc_info=True)
            return False, None, "failed_no_models"

        with self.lock:
            # 1. Attempt local load of requested model
            try:
                logging.info(f"Attempting local load for requested model '{size}'...")
                self.model = WhisperModel(size, device="auto", compute_type="default", local_files_only=True)
                self.model_size = size
                logging.info(f"Faster-Whisper model '{size}' loaded from local cache.")
                return True, size, "loaded_local"
            except Exception as local_err:
                logging.info(f"Local load failed for '{size}' ({local_err}). Checking remote download...")

            # 2. Attempt remote download of requested model
            try:
                logging.info(f"Attempting remote download and load for '{size}'...")
                self.model = WhisperModel(size, device="auto", compute_type="default", local_files_only=False)
                self.model_size = size
                logging.info(f"Faster-Whisper model '{size}' successfully downloaded and loaded.")
                return True, size, "downloaded"
            except Exception as download_err:
                logging.warning(f"Remote download failed for '{size}' ({download_err}). Initiating local fallback search...")

            # 3. Fallback to any other locally available model
            candidates = self._get_fallback_candidates(size)
            for candidate in candidates:
                try:
                    logging.info(f"Attempting local fallback to '{candidate}'...")
                    self.model = WhisperModel(candidate, device="auto", compute_type="default", local_files_only=True)
                    self.model_size = candidate
                    logging.info(f"Faster-Whisper fallback model '{candidate}' loaded from local cache.")
                    return True, candidate, "fallback_local"
                except Exception:
                    continue

            # 4. Total failure (no local models, no internet)
            self.model = None
            logging.error("Failed to initialize any Faster-Whisper model (no local models cached and no network connection).")
            return False, None, "failed_no_models"

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
            Tuple of (segments list, info metadata).
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

        with self.lock:
            segments_gen, info = self.model.transcribe(audio_float32, **kwargs)
            return list(segments_gen), info

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

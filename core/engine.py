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
        self.device: str = "auto"
        self.compute_type: str = "default"
        self.cpu_threads: int = 0
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

    def load_model(self, size: str, config: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str], str]:
        """Load Faster-Whisper model with multi-tier fallback resolution and hardware backend config.

        Sequence:
        1. Attempt local cached load for requested model (local_files_only=True).
        2. Attempt remote download for requested model (local_files_only=False).
        3. Fallback to any other locally cached Whisper model (local_files_only=True).
        4. Fail gracefully if no models and no internet connection.

        Args:
            size: Model size name (e.g. tiny, base, small, medium, large-v3).
            config: Optional configuration dictionary for backend options (device, compute_type, cpu_threads).

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

        requested_device = config.get("whisper_device", "auto") if config else "auto"
        requested_compute = config.get("whisper_compute_type", "default") if config else "default"
        cpu_threads = int(config.get("whisper_cpu_threads", 0)) if config else 0

        # Build list of devices to try: first requested, then cpu fallback if requested != "cpu"
        devices_to_try = [requested_device]
        if requested_device != "cpu":
            devices_to_try.append("cpu")

        with self.lock:
            for dev in devices_to_try:
                comp = requested_compute if dev == requested_device else "default"
                logging.info(f"Attempting to load model '{size}' on device='{dev}' (compute_type='{comp}', cpu_threads={cpu_threads})...")

                # 1. Attempt local load of requested model
                try:
                    self.model = WhisperModel(size, device=dev, compute_type=comp, cpu_threads=cpu_threads, local_files_only=True)
                    self.model_size = size
                    self.device = dev
                    self.compute_type = comp
                    self.cpu_threads = cpu_threads
                    logging.info(f"Faster-Whisper model '{size}' loaded from local cache on device '{dev}'.")
                    return True, size, "loaded_local"
                except Exception as local_err:
                    logging.info(f"Local load on '{dev}' failed for '{size}' ({local_err}). Checking remote download...")

                # 2. Attempt remote download of requested model
                try:
                    self.model = WhisperModel(size, device=dev, compute_type=comp, cpu_threads=cpu_threads, local_files_only=False)
                    self.model_size = size
                    self.device = dev
                    self.compute_type = comp
                    self.cpu_threads = cpu_threads
                    logging.info(f"Faster-Whisper model '{size}' successfully downloaded and loaded on device '{dev}'.")
                    return True, size, "downloaded"
                except Exception as download_err:
                    logging.warning(f"Remote download/load on '{dev}' failed for '{size}' ({download_err}).")

            # 3. Fallback candidates search on CPU
            candidates = self._get_fallback_candidates(size)
            for candidate in candidates:
                try:
                    logging.info(f"Attempting local fallback to '{candidate}' on device 'cpu'...")
                    self.model = WhisperModel(candidate, device="cpu", compute_type="default", cpu_threads=cpu_threads, local_files_only=True)
                    self.model_size = candidate
                    self.device = "cpu"
                    self.compute_type = "default"
                    self.cpu_threads = cpu_threads
                    logging.info(f"Faster-Whisper fallback model '{candidate}' loaded on 'cpu' from local cache.")
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
        """Execute Faster-Whisper transcription on a float32 audio array with expert tuning parameters.

        Args:
            audio_float32: Normalized 16kHz float32 audio sample array.
            config: Configuration dictionary containing inference and VAD settings.
            initial_prompt: Optional previous text context.

        Returns:
            Tuple of (segments list, info metadata).
        """
        if not self.model:
            raise RuntimeError("Faster-Whisper model is not loaded.")

        vad_filter = config.get("vad_filter", False)
        kwargs: Dict[str, Any] = {
            "beam_size": int(config.get("beam_size", 5)),
            "patience": float(config.get("beam_patience", 1.0)),
            "length_penalty": float(config.get("length_penalty", 1.0)),
            "repetition_penalty": float(config.get("repetition_penalty", 1.1)),
            "no_repeat_ngram_size": int(config.get("no_repeat_ngram_size", 0)),
            "condition_on_previous_text": bool(config.get("condition_on_previous_text", True)),
            "word_timestamps": True,
            "vad_filter": vad_filter
        }

        silence_thresh = float(config.get("hallucination_silence_threshold", 2.0))
        if silence_thresh > 0.0:
            kwargs["hallucination_silence_threshold"] = silence_thresh

        if vad_filter:
            vad_params = {
                "threshold": float(config.get("vad_threshold", 0.5)),
                "min_speech_duration_ms": int(config.get("vad_min_speech_duration_ms", 250)),
                "min_silence_duration_ms": int(config.get("vad_min_silence_duration_ms", 2000)),
                "speech_pad_ms": int(config.get("vad_speech_pad_ms", 400)),
            }
            kwargs["vad_parameters"] = vad_params

        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt

        lang = config.get("language", "auto")
        if lang != "auto":
            kwargs["language"] = lang

        temp = float(config.get("temperature", 0.0))
        if temp <= 0.0:
            kwargs["temperature"] = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
        else:
            # Dynamic fallback ladder starting at user temperature up to 1.0
            fallback_ladder = [temp]
            curr = round(temp + 0.2, 2)
            while curr <= 1.0:
                fallback_ladder.append(curr)
                curr = round(curr + 0.2, 2)
            kwargs["temperature"] = fallback_ladder if len(fallback_ladder) > 1 else temp

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

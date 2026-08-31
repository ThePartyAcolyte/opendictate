"""
Real-time Speech-to-Text streaming engine using Google Gemini Live API.

Supports bidirectional WebSocket audio streaming (gemini-3.5-transcribe-live)
with interim partial subtitles, smart/verbatim transcription formatting,
and zero-latency turn finalization.
"""

import asyncio
import logging
import threading
import time
from typing import Dict, Any, Optional, Callable, List


class GeminiLiveEngine:
    """Manages Live API WebSocket session for real-time PCM audio transcription."""

    def __init__(self) -> None:
        """Initialize Gemini Live STT engine state."""
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._audio_queue: Optional[asyncio.Queue] = None
        self._session = None
        self._is_active: bool = False
        self._lock = threading.Lock()

        self.on_interim_text: Optional[Callable[[str], None]] = None
        self.on_final_text: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None

        self.current_model: str = "gemini-3.5-transcribe-live"
        self.current_mode: str = "SMART"
        self.accumulated_text: str = ""
        self._stream_end_requested: bool = False
        self._final_event: threading.Event = threading.Event()

    def is_active(self) -> bool:
        """Check if an active streaming session is running.

        Returns:
            True if session is actively streaming audio, False otherwise.
        """
        return self._is_active

    def start_session(
        self,
        api_key: str,
        config: Dict[str, Any],
        on_interim_text: Optional[Callable[[str], None]] = None,
        on_final_text: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ) -> bool:
        """Start a new bidirectional streaming session in a dedicated background thread.

        Args:
            api_key: Valid Google Gemini API key.
            config: Daemon configuration dictionary.
            on_interim_text: Callback for speculative real-time partial hypotheses.
            on_final_text: Callback for authoritative finalized speech segments.
            on_error: Callback for connection or streaming exceptions.

        Returns:
            True if session initialization started successfully.
        """
        with self._lock:
            if self._is_active:
                logging.warning("GeminiLiveEngine: Session is already active.")
                return True

            self.on_interim_text = on_interim_text
            self.on_final_text = on_final_text
            self.on_error = on_error
            self.current_model = config.get("gemini_live_model", "gemini-3.5-transcribe-live")
            self.current_mode = config.get("gemini_live_mode", "SMART")
            self.accumulated_text = ""
            self._is_active = True
            self._stream_end_requested = False
            self._final_event = threading.Event()

            ready_event = threading.Event()
            self._thread = threading.Thread(
                target=self._run_event_loop,
                args=(api_key, config, ready_event),
                daemon=True,
                name="GeminiLiveEngineThread"
            )
            self._thread.start()

            # Wait for event loop initialization
            ready_event.wait(timeout=3.0)
            return True

    def _run_event_loop(self, api_key: str, config: Dict[str, Any], ready_event: threading.Event) -> None:
        """Entry point for the dedicated background asyncio event loop thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._audio_queue = asyncio.Queue()
        ready_event.set()

        try:
            self._loop.run_until_complete(self._session_lifecycle(api_key, config))
        except Exception as e:
            logging.error(f"GeminiLiveEngine event loop error: {e}", exc_info=True)
            if self.on_error:
                self.on_error(e)
        finally:
            self._is_active = False
            self._final_event.set()
            try:
                self._loop.close()
            except Exception:
                pass
            logging.info("GeminiLiveEngine event loop terminated.")

    async def _session_lifecycle(self, api_key: str, config: Dict[str, Any]) -> None:
        """Manage connection, audio pump task, and receive stream task."""
        from google import genai
        from google.genai import types

        lang = config.get("language", "auto")
        lang_codes: List[str] = []
        if lang and lang != "auto":
            lang_codes = [lang]

        mode_setting = self.current_mode.upper() if self.current_mode in ["SMART", "VERBATIM"] else "SMART"

        try:
            audio_transcription_cfg = types.AudioTranscriptionConfig(
                language_codes=lang_codes,
                mode=mode_setting
            )
        except Exception:
            audio_transcription_cfg = types.AudioTranscriptionConfig(
                language_codes=lang_codes
            )

        connect_config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            input_audio_transcription=audio_transcription_cfg
        )

        client = genai.Client(api_key=api_key)
        logging.info(f"GeminiLiveEngine: Connecting to Live API (model='{self.current_model}', mode='{mode_setting}')...")

        try:
            async with client.aio.live.connect(model=self.current_model, config=connect_config) as session:
                self._session = session
                logging.info("GeminiLiveEngine: WebSocket connection established successfully.")

                sender_task = asyncio.create_task(self._sender_loop(session))
                receiver_task = asyncio.create_task(self._receiver_loop(session))

                # Run until both finish or stream end terminates receiver
                done, pending = await asyncio.wait(
                    [sender_task, receiver_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()

        except Exception as err:
            logging.error(f"GeminiLiveEngine connection exception: {err}", exc_info=True)
            if self.on_error:
                self.on_error(err)
            raise

    async def _sender_loop(self, session: Any) -> None:
        """Stream PCM audio chunks from queue to WebSocket."""
        from google.genai import types

        while self._is_active:
            try:
                # Wait for audio chunk with small timeout to allow checking self._is_active
                chunk = await asyncio.wait_for(self._audio_queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                continue

            if chunk is None:
                # Sentinel signaling stream end
                logging.info("GeminiLiveEngine: Sending audio_stream_end signal.")
                try:
                    await session.send_realtime_input(audio_stream_end=True)
                except Exception as e:
                    logging.warning(f"GeminiLiveEngine error sending stream end: {e}")
                break

            try:
                await session.send_realtime_input(
                    audio=types.Blob(
                        data=chunk,
                        mime_type="audio/pcm;rate=16000"
                    )
                )
            except Exception as e:
                logging.error(f"GeminiLiveEngine send error: {e}")
                if self.on_error:
                    self.on_error(e)
                break

    async def _receiver_loop(self, session: Any) -> None:
        """Receive real-time transcription events from WebSocket server."""
        try:
            async for response in session.receive():
                server_content = response.server_content
                if not server_content:
                    continue

                # 1. Speculative interim hypothesis (live typing feedback)
                if server_content.interim_input_transcription:
                    interim = server_content.interim_input_transcription.text
                    if interim and self.on_interim_text and self._is_active:
                        self.on_interim_text(interim)

                # 2. Finalized authoritative transcript segment
                if server_content.input_transcription:
                    final_part = server_content.input_transcription.text
                    if final_part:
                        if self.accumulated_text and not self.accumulated_text.endswith(" ") and not final_part.startswith(" "):
                            self.accumulated_text += " "
                        self.accumulated_text += final_part
                        if self.on_final_text and self._is_active:
                            self.on_final_text(self.accumulated_text)

                    if self._stream_end_requested:
                        self._final_event.set()
                        # Short delay to allow any subsequent final chunk before closing
                        await asyncio.sleep(0.15)
                        break

                if server_content.turn_complete and self._stream_end_requested:
                    self._final_event.set()
                    break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"GeminiLiveEngine receive error: {e}")
            if self.on_error:
                self.on_error(e)
            self._final_event.set()

    def send_audio_chunk(self, pcm_bytes: bytes) -> None:
        """Enqueue PCM audio chunk for live streaming.

        Args:
            pcm_bytes: Raw 16-bit 16kHz PCM audio bytes.
        """
        if not self._is_active or not self._loop or not self._audio_queue:
            return

        try:
            self._loop.call_soon_threadsafe(self._audio_queue.put_nowait, pcm_bytes)
        except Exception as e:
            logging.debug(f"GeminiLiveEngine failed to enqueue audio chunk: {e}")

    def stop_session(self, timeout: float = 2.0) -> str:
        """Signal end of audio stream, wait for final transcript, and close session.

        Args:
            timeout: Maximum seconds to wait for final server response.

        Returns:
            Full accumulated finalized transcript text.
        """
        with self._lock:
            if not self._is_active:
                return self.accumulated_text.strip()

            logging.info("GeminiLiveEngine: Stopping session and requesting finalization...")
            self._stream_end_requested = True
            if self._loop and self._audio_queue:
                self._loop.call_soon_threadsafe(self._audio_queue.put_nowait, None)

            # Wait for final server transcription event with minimal latency
            self._final_event.wait(timeout=timeout)

            self._is_active = False
            result = self.accumulated_text.strip()
            logging.info(f"GeminiLiveEngine: Session stopped. Final transcript: '{result}'")
            return result

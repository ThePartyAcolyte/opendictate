"""
LLM text post-processing and vision integration module for OpenDictate.

Uses Google Gemini GenAI SDK to clean, format, and punctuate raw voice dictations.
"""

import os
import time
import subprocess
import logging
from typing import Dict, Any, Optional, Callable
from core.config import ConfigManager

DEFAULT_BASE_PROMPT = (
    "You are a real-time voice dictation assistant.\n"
    "Your objective is to clean up the following voice-dictated text, correcting obvious speech recognition errors and punctuation, while keeping it as faithful to the original as possible.\n"
    "If the text includes verbal formatting instructions (e.g. 'open parenthesis', 'new line', 'comma', 'period'), apply them.\n"
    "Use capitalization when appropriate and correct homophones based on context to make sense of the text without changing the original words or adding extra text.\n"
    "CRITICAL: You MUST reply in the EXACT SAME LANGUAGE as the dictated text. Do not translate it. For example, if the input is in Spanish, output in Spanish.\n"
    "Return ONLY the corrected text, without greetings, explanations or translations."
)


class LLMService:
    """Manages Gemini LLM connections, prompt enrichment, and vision attachments."""

    def __init__(self, config_manager: ConfigManager) -> None:
        """Initialize LLM service with configuration manager reference.

        Args:
            config_manager: ConfigManager instance.
        """
        self.config_manager = config_manager

    def clean_text(
        self,
        text: str,
        config: Dict[str, Any],
        app_class: str,
        on_chunk: Optional[Callable[[str], None]] = None
    ) -> str:
        """Process dictated text using Gemini API with contextual prompts and vision input.

        Args:
            text: Raw transcribed text string.
            config: Current configuration dictionary.
            app_class: Target window class name.
            on_chunk: Optional callback for streaming tokens to UI.

        Returns:
            Cleaned and formatted text string.
        """
        api_key = config.get("api_key", "").strip()
        if not api_key:
            logging.warning("No Gemini API Key provided. Returning original text.")
            return text

        try:
            from google import genai
            from google.genai import types

            char_count = len(text)
            default_timeout = int(max(120.0, (char_count / 1000.0) * 120.0) * 1000)
            timeout_ms = int(config.get("llm_timeout", 120)) * 1000
            if timeout_ms < default_timeout:
                timeout_ms = default_timeout

            client = genai.Client(
                api_key=api_key,
                http_options={'timeout': timeout_ms}
            )

            base_prompt = config.get("base_system_prompt", DEFAULT_BASE_PROMPT)
            prompt_parts = [base_prompt]

            # Fetch App Profile and Vision config
            app_prompt, enable_vision = self.config_manager.get_app_profile(app_class)
            if app_prompt:
                prompt_parts.append(f"Specific context for this application ({app_class}): {app_prompt}")

            if enable_vision:
                shot_path = "/tmp/dictate_vision.png"
                try:
                    res = subprocess.run(["wl-paste", "-t", "image/png"], capture_output=True)
                    if res.returncode == 0 and len(res.stdout) > 0:
                        with open(shot_path, "wb") as f:
                            f.write(res.stdout)

                        my_file = client.files.upload(file=shot_path)
                        prompt_parts.append("Below is a context image (screenshot or image copied to clipboard):")
                        prompt_parts.append(my_file)
                        logging.info("Clipboard image attached successfully to LLM prompt.")
                except Exception as e:
                    logging.error(f"Error attaching clipboard image for vision: {e}")

            # Fetch recent dictation history
            history_rows = self.config_manager.get_recent_history(app_class, limit=3)
            if history_rows:
                hist_text = "Recent dictation history in this application (reference context only, DO NOT repeat):\n"
                for h_llm, h_orig in reversed(history_rows):
                    ref_text = h_llm if h_llm else h_orig
                    if ref_text:
                        hist_text += f"- {ref_text}\n"
                prompt_parts.append(hist_text)

            prompt_parts.append(f"Text to correct NOW:\n{text}")

            model_name = config.get("model", "gemini-3.1-flash-live-preview")
            is_live_model = "live" in model_name.lower()

            if is_live_model:
                return self._clean_text_live(
                    client=client,
                    model_name=model_name,
                    prompt_parts=prompt_parts,
                    config=config,
                    on_chunk=on_chunk
                )
            else:
                gen_config = types.GenerateContentConfig(
                    temperature=float(config.get("llm_temperature", 0.7))
                )
                if config.get("llm_thinking", False):
                    gen_config.thinking_config = types.ThinkingConfig(thinking_budget=-1)

                response = client.models.generate_content_stream(
                    model=model_name,
                    contents=prompt_parts,
                    config=gen_config
                )

                cleaned_text = ""
                for chunk in response:
                    if chunk.text:
                        cleaned_text += chunk.text
                        if on_chunk:
                            on_chunk(cleaned_text)

                return cleaned_text.strip() if cleaned_text else text

        except Exception as e:
            logging.error(f"Gemini LLM processing error: {e}", exc_info=True)
            return text

    def _clean_text_live(
        self,
        client: Any,
        model_name: str,
        prompt_parts: list,
        config: Dict[str, Any],
        on_chunk: Optional[Callable[[str], None]] = None
    ) -> str:
        """Process text cleanup using Gemini Live API WebSocket session.

        Args:
            client: genai.Client instance.
            model_name: Live model identifier.
            prompt_parts: Context and text prompt elements.
            config: Application configuration dictionary.
            on_chunk: Optional callback for streaming tokens to UI.

        Returns:
            Cleaned text string.
        """
        import asyncio
        from google.genai import types

        async def _run_live_session() -> str:
            # Build combined text from string prompt parts (files handled separately if present)
            text_payload = ""
            media_files = []
            for part in prompt_parts:
                if isinstance(part, str):
                    text_payload += f"{part}\n\n"
                else:
                    media_files.append(part)

            thinking_level = config.get("llm_thinking_level", "minimal") if config.get("llm_thinking", False) else "minimal"
            live_config = types.LiveConnectConfig(
                response_modalities=["TEXT"],
                generation_config=types.GenerateContentConfig(
                    temperature=float(config.get("llm_temperature", 0.7)),
                    thinking_config=types.ThinkingConfig(thinking_level=thinking_level) if config.get("llm_thinking", False) else None
                )
            )

            cleaned_tokens = []
            async with client.aio.live.connect(model=model_name, config=live_config) as session:
                # Send context files if any
                for media in media_files:
                    await session.send(input=media)

                # Send text correction prompt
                await session.send(input=text_payload.strip(), end_of_turn=True)

                async for response in session.receive():
                    server_content = response.server_content
                    if not server_content:
                        continue

                    if server_content.model_turn:
                        for part in server_content.model_turn.parts:
                            if part.text:
                                cleaned_tokens.append(part.text)
                                if on_chunk:
                                    on_chunk("".join(cleaned_tokens))

                    if server_content.turn_complete:
                        break

            return "".join(cleaned_tokens).strip()

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run_live_session())
        finally:
            loop.close()

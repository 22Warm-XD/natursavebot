from __future__ import annotations

import asyncio

from src.config import Settings


class GeminiProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_key = settings.secret_value(settings.gemini_api_key)

    async def generate_text(self, prompt: str, *, system: str = "", max_tokens: int = 700) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is empty")

        def run() -> str:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.settings.gemini_model, system_instruction=system or None)
            response = model.generate_content(prompt, generation_config={"max_output_tokens": max_tokens, "temperature": 0.2})
            return response.text or ""

        return await asyncio.to_thread(run)

    async def transcribe(self, file_path: str) -> str:
        raise RuntimeError("Gemini transcription is not implemented in this MVP; use OpenAI Whisper")

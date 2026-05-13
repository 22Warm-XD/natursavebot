from __future__ import annotations

from src.config import Settings


class OpenAIProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_key = settings.secret_value(settings.openai_api_key)

    def _client(self):
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is empty")
        from openai import AsyncOpenAI

        return AsyncOpenAI(api_key=self.api_key)

    async def generate_text(self, prompt: str, *, system: str = "", max_tokens: int = 700) -> str:
        client = self._client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = await client.chat.completions.create(
            model=self.settings.openai_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return response.choices[0].message.content or ""

    async def transcribe(self, file_path: str) -> str:
        client = self._client()
        with open(file_path, "rb") as file_obj:
            response = await client.audio.transcriptions.create(
                model=self.settings.openai_transcribe_model,
                file=file_obj,
            )
        return getattr(response, "text", "") or ""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str


class LLMProvider(Protocol):
    async def generate_text(self, prompt: str, *, system: str = "", max_tokens: int = 700) -> str:
        ...

    async def transcribe(self, file_path: str) -> str:
        ...

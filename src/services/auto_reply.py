from __future__ import annotations

import time

from src.services.llm.router import LLMRouter


class AutoReplyGate:
    def __init__(self) -> None:
        self._last_sent: dict[int, float] = {}

    def allowed(self, chat_id: int, cooldown_seconds: int) -> bool:
        now = time.time()
        last = self._last_sent.get(chat_id, 0)
        if now - last < cooldown_seconds:
            return False
        self._last_sent[chat_id] = now
        return True


async def build_auto_reply(mode: str, static_text: str, incoming_text: str, llm: LLMRouter) -> str:
    if mode != "smart":
        return static_text
    return await llm.generate_text(
        incoming_text,
        system=(
            "Составь короткий вежливый ответ в личном стиле владельца. "
            "Не обещай лишнего, не отправляй секреты, максимум 350 символов."
        ),
        max_tokens=160,
    )

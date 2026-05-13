from __future__ import annotations

from src.services.llm.router import LLMRouter


class AgentRouter:
    def __init__(self, llm: LLMRouter) -> None:
        self.llm = llm

    async def route(self, text: str) -> dict:
        return await self.llm.classify_intent(text)

from __future__ import annotations

from src.config import Settings
from src.services.llm.router import LLMRouter


class FakeProvider:
    def __init__(self, response: str = '{"intent":"search_messages","query":"договор"}', *, fail: bool = False) -> None:
        self.prompts: list[str] = []
        self.response = response
        self.fail = fail

    async def generate_text(self, prompt: str, *, system: str = "", max_tokens: int = 700) -> str:
        if self.fail:
            raise RuntimeError("provider is down")
        self.prompts.append(prompt)
        return self.response

    async def transcribe(self, file_path: str) -> str:
        return "voice text"


async def test_heuristic_send_message_does_not_call_provider() -> None:
    fake = FakeProvider()
    router = LLMRouter(Settings(_env_file=None), provider=fake)

    result = await router.classify_intent("Напиши Олегу, что созвон в 8")

    assert result["intent"] == "send_message"
    assert result["recipient"] == "Олегу"
    assert result["text"] == "созвон в 8"
    assert fake.prompts == []


async def test_unknown_falls_back_to_provider_json() -> None:
    fake = FakeProvider()
    router = LLMRouter(Settings(_env_file=None), provider=fake)

    result = await router.classify_intent("в какой переписке был договор")

    assert result == {"intent": "search_messages", "query": "договор"}
    assert fake.prompts


async def test_fenced_json_is_parsed() -> None:
    fake = FakeProvider("```json\n{\"intent\":\"digest\"}\n```")
    router = LLMRouter(Settings(_env_file=None), provider=fake)

    result = await router.classify_intent("что-то непонятное")

    assert result == {"intent": "digest"}


async def test_bad_provider_response_returns_unknown() -> None:
    fake = FakeProvider("not json")
    router = LLMRouter(Settings(_env_file=None), provider=fake)

    result = await router.classify_intent("что-то непонятное")

    assert result == {"intent": "unknown"}


async def test_provider_exception_returns_unknown() -> None:
    fake = FakeProvider(fail=True)
    router = LLMRouter(Settings(_env_file=None), provider=fake)

    result = await router.classify_intent("что-то непонятное")

    assert result == {"intent": "unknown"}

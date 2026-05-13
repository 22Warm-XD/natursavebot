from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Summary
from src.db.repositories.messages import recent_messages
from src.services.llm.router import LLMRouter


def format_message_for_llm(sender: str | None, text: str | None) -> str:
    sender_label = sender or "unknown"
    return f"{sender_label}: {text or ''}"


async def summarize_chat(session: AsyncSession, llm: LLMRouter, chat_id: int, *, kind: str = "summary", limit: int = 80) -> str:
    messages = await recent_messages(session, chat_id, limit=limit)
    lines = [format_message_for_llm(msg.sender_name if msg.direction == "incoming" else "me", msg.text) for msg in messages if msg.text]
    if not lines:
        return "Нет текстовых сообщений для выжимки."
    summary = await llm.summarize(lines)
    session.add(
        Summary(
            chat_id=chat_id,
            kind=kind,
            text=summary,
            from_date=messages[0].date if messages else None,
            to_date=messages[-1].date if messages else None,
        )
    )
    await session.flush()
    return summary

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Message
from src.services.llm.router import LLMRouter


async def build_digest(session: AsyncSession, llm: LLMRouter, *, hours: int = 24, limit: int = 120) -> str:
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)
    stmt = select(Message).where(Message.date >= since, Message.text.is_not(None)).order_by(desc(Message.date)).limit(limit)
    messages = list((await session.execute(stmt)).scalars())
    if not messages:
        return "За выбранный период нет новых текстовых сообщений."
    lines = [
        f"{msg.chat_title or msg.chat_id} · {msg.sender_name or msg.direction}: {msg.text}"
        for msg in reversed(messages)
        if msg.text
    ]
    return await llm.generate_text(
        "\n".join(lines),
        system=(
            "Сделай личный Telegram-дайджест: что писали, что обсуждали, "
            "что требует ответа, задачи/дедлайны, важные сообщения. Кратко."
        ),
        max_tokens=900,
    )

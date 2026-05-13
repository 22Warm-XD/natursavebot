from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Reminder


async def create_reminder(
    session: AsyncSession,
    *,
    text_value: str,
    remind_at: datetime,
    lead_minutes: int | None = None,
    chat_id: int | None = None,
    message_id: int | None = None,
) -> Reminder:
    reminder = Reminder(
        text=text_value,
        remind_at=remind_at,
        lead_minutes=lead_minutes,
        chat_id=chat_id,
        message_id=message_id,
    )
    session.add(reminder)
    await session.flush()
    return reminder


async def due_reminders(session: AsyncSession, now: datetime) -> list[Reminder]:
    stmt = select(Reminder).where(Reminder.status == "open", Reminder.remind_at <= now)
    return list((await session.execute(stmt)).scalars())


async def open_reminders(session: AsyncSession, *, limit: int = 50) -> list[Reminder]:
    stmt = select(Reminder).where(Reminder.status == "open").order_by(Reminder.remind_at.asc()).limit(limit)
    return list((await session.execute(stmt)).scalars())


async def set_reminder_status(session: AsyncSession, reminder_id: int, status: str) -> Reminder | None:
    reminder = await session.get(Reminder, reminder_id)
    if reminder:
        reminder.status = status
        if status in {"done", "cancelled"}:
            reminder.last_ping_at = datetime.now(UTC).replace(tzinfo=None)
        await session.flush()
    return reminder

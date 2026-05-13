from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.config import Settings
from src.db.repositories.reminders import create_reminder, open_reminders
from src.db.session import get_session
from src.utils.timeparse import parse_reminder_phrase


router = Router(name="reminders")


@router.message(Command("remind"))
async def cmd_remind(message: Message, settings: Settings) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /remind завтра в 18:00 позвонить")
        return
    parsed = parse_reminder_phrase(parts[1], tz_name=settings.timezone)
    if not parsed:
        await message.answer("Не понял дату. Пример: /remind завтра в 18:00 позвонить")
        return
    async with get_session() as session:
        reminder = await create_reminder(session, text_value=parsed.text, remind_at=parsed.when)
        await session.commit()
    await message.answer(f"Напоминание #{reminder.id}: <code>{parsed.when.isoformat(sep=' ', timespec='minutes')} UTC</code>\n{parsed.text}")


@router.message(Command("reminders"))
async def cmd_reminders(message: Message) -> None:
    async with get_session() as session:
        rows = await open_reminders(session)
    if not rows:
        await message.answer("Открытых напоминаний нет.")
        return
    await message.answer(
        "<b>Напоминания</b>\n"
        + "\n".join(f"#{item.id} · {item.remind_at.isoformat(sep=' ', timespec='minutes')} UTC · {item.text}" for item in rows[:20])
    )

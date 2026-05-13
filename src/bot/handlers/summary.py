from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.db.repositories.chats import find_chats
from src.db.session import get_session
from src.services.llm.router import LLMRouter
from src.services.summarizer import summarize_chat


router = Router(name="summary")


@router.message(Command("summary"))
async def cmd_summary(message: Message, llm: LLMRouter) -> None:
    await _summary_command(message, llm, kind="summary")


@router.message(Command("catchup"))
async def cmd_catchup(message: Message, llm: LLMRouter) -> None:
    await _summary_command(message, llm, kind="catchup")


async def _summary_command(message: Message, llm: LLMRouter, *, kind: str) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(f"Формат: /{kind} чат")
        return
    async with get_session() as session:
        chats = await find_chats(session, parts[1], limit=1)
        if not chats:
            await message.answer("Чат не найден. В Business mode он появится после первого сообщения, доступного боту.")
            return
        summary = await summarize_chat(session, llm, chats[0].chat_id, kind=kind)
        await session.commit()
    title = chats[0].title or str(chats[0].chat_id)
    label = "Где остановились" if kind == "catchup" else "Краткая выжимка"
    await message.answer(f"<b>{label}: {title}</b>\n{summary}")

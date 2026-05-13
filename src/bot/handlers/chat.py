from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.db.repositories.chats import find_chats
from src.db.repositories.messages import recent_messages
from src.db.session import get_session
from src.utils.text import clip


router = Router(name="chat")


@router.message(Command("chat"))
async def cmd_chat(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат: /chat имя, username или chat_id")
        return
    query = parts[1].strip()
    async with get_session() as session:
        chats = await find_chats(session, query, limit=10)
        if not chats and query.lstrip("-").isdigit():
            from src.db.repositories.chats import get_chat_by_id

            chat = await get_chat_by_id(session, int(query))
            chats = [chat] if chat else []
        if not chats:
            await message.answer("Чат не найден. В Business mode он появится после первого business_message.")
            return
        chat = chats[0]
        recent = await recent_messages(session, chat.chat_id, limit=3)
    lines = [
        f"<b>{chat.title or chat.chat_id}</b>",
        f"Chat ID: <code>{chat.chat_id}</code>",
        f"Username: <code>{('@' + chat.username) if chat.username else '-'}</code>",
        f"Type: <code>{chat.chat_type}</code>",
        "",
        "<b>Последние сообщения:</b>",
    ]
    lines.extend(f"- {clip(row.text or row.caption or '[медиа]', 120)}" for row in recent)
    await message.answer("\n".join(lines))

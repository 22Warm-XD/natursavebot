from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from telethon import utils
from telethon.errors import FloodWaitError

from src.config import Settings
from src.db.repositories.chats import upsert_chat
from src.db.repositories.messages import search_messages, upsert_message
from src.db.session import get_session
from src.services.search import format_search_result
from src.userbot.client import UserbotManager


router = Router(name="search")


@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    query = (message.text or "").split(maxsplit=1)
    if len(query) < 2:
        await message.answer("Формат: /search текст")
        return
    async with get_session() as session:
        rows = await search_messages(session, query[1], limit=15)
    if not rows:
        await message.answer("В локальной базе ничего не найдено.")
        return
    await message.answer("<b>Найдено</b>\n" + "\n\n".join(format_search_result(row) for row in rows))


@router.message(Command("sync"))
async def cmd_sync(message: Message, userbot: UserbotManager, settings: Settings) -> None:
    if settings.telegram_mode == "business":
        await message.answer("В Business mode синхронизация не нужна: бот сохраняет новые business messages автоматически.")
        return
    client = userbot.get_client()
    if client is None:
        await message.answer("Legacy userbot не подключён. Используй /login только в TELEGRAM_MODE=userbot или both.")
        return
    synced_chats = 0
    synced_messages = 0
    try:
        async for dialog in client.iter_dialogs(limit=settings.sync_dialog_limit):
            if settings.ignore_archived_chats and getattr(dialog, "archived", False):
                continue
            entity = dialog.entity
            chat_id = utils.get_peer_id(entity)
            if chat_id is None:
                continue
            async with get_session() as session:
                await upsert_chat(
                    session,
                    chat_id=chat_id,
                    title=getattr(dialog, "name", None) or getattr(entity, "title", None),
                    username=getattr(entity, "username", None),
                    chat_type="channel" if getattr(entity, "broadcast", False) else ("group" if getattr(entity, "title", None) else "private"),
                    is_archived=bool(getattr(dialog, "archived", False)),
                    is_bot=bool(getattr(entity, "bot", False)),
                )
                async for msg in client.iter_messages(entity, limit=settings.sync_messages_per_chat):
                    sender = await msg.get_sender() if msg.sender_id else None
                    await upsert_message(
                        session,
                        chat_id=chat_id,
                        message_id=msg.id,
                        sender_id=msg.sender_id,
                        sender_name=_name(sender),
                        sender_username=getattr(sender, "username", None),
                        chat_title=getattr(dialog, "name", None),
                        direction="outgoing" if msg.out else "incoming",
                        text_value=msg.text or msg.message or None,
                        date=msg.date.replace(tzinfo=None) if msg.date else datetime.now(UTC).replace(tzinfo=None),
                        reply_to=getattr(msg.reply_to, "reply_to_msg_id", None),
                    )
                    synced_messages += 1
                await session.commit()
            synced_chats += 1
    except FloodWaitError as exc:
        await message.answer(f"Telegram FloodWait: подожди {exc.seconds} сек. Уже обновлено чатов: {synced_chats}.")
        return
    await message.answer(f"Legacy sync готов: {synced_chats} чатов, {synced_messages} сообщений.")


def _name(sender) -> str | None:
    if sender is None:
        return None
    parts = [getattr(sender, "first_name", None), getattr(sender, "last_name", None)]
    return " ".join(part for part in parts if part).strip() or getattr(sender, "username", None)

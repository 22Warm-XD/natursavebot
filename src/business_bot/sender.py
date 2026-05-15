from __future__ import annotations

from aiogram import Bot
from aiogram.methods import DeleteBusinessMessages, SendChatAction, SendMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.business_bot.connection import latest_business_connection
from src.config import Settings
from src.db.models import BusinessConnection, DraftMessage


async def send_business_message(
    bot: Bot,
    *,
    business_connection_id: str,
    chat_id: int,
    text: str,
    reply_to_message_id: int | None = None,
    parse_mode: str | None = None,
) -> object:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "business_connection_id": business_connection_id,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        return await bot.send_message(**payload)
    except TypeError:
        method = SendMessage(**payload)
        return await bot(method)


async def send_business_chat_action(
    bot: Bot,
    *,
    business_connection_id: str,
    chat_id: int,
    action: str = "typing",
) -> object:
    payload = {
        "chat_id": chat_id,
        "action": action,
        "business_connection_id": business_connection_id,
    }
    try:
        return await bot.send_chat_action(**payload)
    except TypeError:
        method = SendChatAction(**payload)
        return await bot(method)


async def delete_business_messages(
    bot: Bot,
    *,
    business_connection_id: str,
    message_ids: list[int],
) -> object:
    payload = {
        "business_connection_id": business_connection_id,
        "message_ids": message_ids,
    }
    try:
        return await bot.delete_business_messages(**payload)
    except TypeError:
        method = DeleteBusinessMessages(**payload)
        return await bot(method)


async def send_business_draft(bot: Bot, session: AsyncSession, draft: DraftMessage, settings: Settings) -> None:
    connection = None
    if draft.business_connection_id:
        connection = (
            await session.execute(
                select(BusinessConnection).where(BusinessConnection.connection_id == draft.business_connection_id)
            )
        ).scalar_one_or_none()
    if connection is None:
        connection = await latest_business_connection(session)
    if connection is None or not connection.connection_id:
        raise RuntimeError("Telegram Business ещё не подключён.")
    if connection.user_id != settings.owner_telegram_id:
        raise RuntimeError("Business connection не принадлежит владельцу.")
    if not connection.is_enabled:
        raise RuntimeError("Business connection выключен в Telegram.")
    if connection.can_reply is False:
        raise RuntimeError("У бота нет права отвечать от имени Business-аккаунта.")
    await send_business_message(
        bot,
        business_connection_id=connection.connection_id,
        chat_id=draft.chat_id,
        text=draft.text,
    )

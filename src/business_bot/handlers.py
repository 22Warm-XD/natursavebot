from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.types import BusinessConnection, BusinessMessagesDeleted, Message, Update
from sqlalchemy import select

from src.business_bot.connection import save_business_connection
from src.business_bot.media_downloader import download_business_media, has_expiring_media_hint
from src.business_bot.message_saver import save_business_delete, save_business_edit, save_business_message
from src.business_bot.notifications import (
    notify_business_delete,
    notify_business_disabled,
    notify_business_edit,
    notify_business_enabled,
    notify_business_media_saved,
    notify_business_media_unavailable,
)
from src.config import Settings
from src.db.models import BusinessConnection as StoredBusinessConnection
from src.db.repositories.settings import get_all_settings
from src.db.session import get_session
from src.services.save_mode_business import record_business_update


logger = logging.getLogger(__name__)
router = Router(name="business_bot")


@router.business_connection()
async def on_business_connection(connection: BusinessConnection, bot: Bot, settings: Settings) -> None:
    if connection.user.id != settings.owner_telegram_id:
        logger.warning("ignored business connection for unexpected owner id=%s", connection.user.id)
        if settings.owner_telegram_id:
            await bot.send_message(
                settings.owner_telegram_id,
                "Получен business_connection не от владельца. Событие проигнорировано.",
            )
        return
    async with get_session() as session:
        await save_business_connection(session, connection)
        await session.commit()
    if connection.is_enabled:
        await notify_business_enabled(bot, settings)
    else:
        await notify_business_disabled(bot, settings)


@router.business_message()
async def on_business_message(message: Message, bot: Bot, settings: Settings) -> None:
    saved_notice = None
    unavailable_notice = None
    async with get_session() as session:
        if not await _connection_allowed(session, message.business_connection_id, settings):
            return
        if await _notify_business_dot_unavailable(message, bot, settings):
            return
        values = await get_all_settings(session)
        if not values.get("save_mode_enabled", True):
            return
        media = None
        if values.get("save_media_enabled", True):
            media = await download_business_media(bot, message, settings)
        row = await save_business_message(session, message, media, owner_id=settings.owner_telegram_id)
        if media and media.media_type and media.local_path and has_expiring_media_hint(message):
            saved_notice = (row, media, "🕒 Истекающее медиа сохранено")
        elif has_expiring_media_hint(message) and not (getattr(message, "voice", None) or getattr(message, "audio", None)):
            unavailable_notice = (row, media)
        reply_notice = await _save_replied_media_if_owner_reply(session, message, bot, settings, values)
        if reply_notice:
            saved_notice = reply_notice
        await session.commit()
    if saved_notice:
        row, notice_media, title = saved_notice
        await notify_business_media_saved(bot, settings, row, notice_media, title=title)
    elif unavailable_notice:
        row, notice_media = unavailable_notice
        await notify_business_media_unavailable(bot, settings, row, notice_media)


@router.edited_business_message()
async def on_edited_business_message(message: Message, bot: Bot, settings: Settings) -> None:
    async with get_session() as session:
        if not await _connection_allowed(session, message.business_connection_id, settings):
            return
        values = await get_all_settings(session)
        if not values.get("save_mode_enabled", True):
            return
        media = await download_business_media(bot, message, settings) if values.get("save_media_enabled", True) else None
        row, edit, old_text = await save_business_edit(session, message, media, owner_id=settings.owner_telegram_id)
        await session.commit()
    if values.get("save_mode_notify_edits", settings.effective_notify_edits):
        await notify_business_edit(
            bot,
            settings,
            sender_name=getattr(row, "sender_name", None),
            sender_username=getattr(row, "sender_username", None),
            chat_label=getattr(row, "chat_title", None),
            chat_id=getattr(row, "chat_id", None),
            message_date=getattr(row, "edited_at", None) or getattr(row, "date", None),
            old_text=old_text,
            new_text=message.text or message.caption,
        )


@router.deleted_business_messages()
async def on_deleted_business_messages(deleted: BusinessMessagesDeleted, bot: Bot, settings: Settings) -> None:
    async with get_session() as session:
        if not await _connection_allowed(session, deleted.business_connection_id, settings):
            return
        values = await get_all_settings(session)
        if not values.get("save_mode_enabled", True):
            return
        messages, event = await save_business_delete(session, deleted, owner_id=settings.owner_telegram_id)
        await session.commit()
    if event is None:
        return
    if values.get("save_mode_notify_deletes", settings.effective_notify_deletes):
        if not messages:
            logger.info(
                "skip missing deleted business notification chat_id=%s message_ids=%s",
                deleted.chat.id,
                list(deleted.message_ids),
            )
            return
        chat_label = getattr(deleted.chat, "title", None) or getattr(deleted.chat, "username", None) or str(deleted.chat.id)
        for stored in messages:
            await notify_business_delete(bot, settings, stored, chat_label=chat_label)


async def handle_raw_business_update(update: Update | dict) -> bool:
    async with get_session() as session:
        notes = await record_business_update(session, update)
        await session.commit()
    return bool(notes)


async def _connection_allowed(session, connection_id: str | None, settings: Settings) -> bool:
    if not connection_id:
        return False
    connection = (
        await session.execute(
            select(StoredBusinessConnection).where(StoredBusinessConnection.connection_id == connection_id)
        )
    ).scalar_one_or_none()
    return bool(connection and connection.user_id == settings.owner_telegram_id and connection.is_enabled)


async def _notify_business_dot_unavailable(message: Message, bot: Bot, settings: Settings) -> bool:
    if settings.telegram_mode != "business":
        return False
    if not message.from_user or message.from_user.id != settings.owner_telegram_id:
        return False
    text = (message.text or message.caption or "").strip()
    if not text.startswith("."):
        return False
    command = text.split(maxsplit=1)[0].lower()
    if command not in {".mute", ".unmute", ".type", ".spam", ".repeat", ".love", ".info"}:
        return False
    await bot.send_message(
        settings.owner_telegram_id,
        f"<b>{command}</b>: доступно только в userbot/Telethon mode.\n\n"
        "Переключи <code>TELEGRAM_MODE=userbot</code> или <code>TELEGRAM_MODE=both</code> и подключи Telethon через /login.",
    )
    return True


async def _save_replied_media_if_owner_reply(session, message: Message, bot: Bot, settings: Settings, values: dict):
    if not values.get("save_media_enabled", True):
        return None
    if not message.from_user or message.from_user.id != settings.owner_telegram_id:
        return None
    reply = message.reply_to_message
    if reply is None:
        return None
    if not has_expiring_media_hint(reply):
        return None
    media = await download_business_media(bot, reply, settings, allow_voice_audio=True)
    if not media.media_type:
        return None
    row = await save_business_message(session, reply, media, owner_id=settings.owner_telegram_id)
    if media.local_path:
        return row, media, "🕒 Скрытое медиа из ответа сохранено"
    return None

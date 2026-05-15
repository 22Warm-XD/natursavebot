from __future__ import annotations

import logging
import re

from aiogram import Bot, Router
from aiogram.types import BusinessConnection, BusinessMessagesDeleted, Message, Update
from sqlalchemy import select

from src.business_bot.connection import save_business_connection
from src.business_bot.dot_commands import handle_business_dot_command
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
from src.business_bot.sender import delete_business_messages
from src.config import Settings
from src.db.models import BusinessConnection as StoredBusinessConnection
from src.db.repositories.chat_settings import get_chat_setting, hard_mute_active
from src.db.repositories.hard_mute import create_hard_mute_event, update_hard_mute_delete_status
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

        values = await get_all_settings(session)
        save_mode_enabled = values.get("save_mode_enabled", True)
        save_media_enabled = values.get("save_media_enabled", True)

        media = None
        row = None
        if save_mode_enabled:
            if save_media_enabled:
                media = await download_business_media(bot, message, settings)
            row = await save_business_message(session, message, media, owner_id=settings.owner_telegram_id)

            if media and media.media_type and media.local_path and has_expiring_media_hint(message):
                saved_notice = (row, media, "🕒 Истекающее медиа сохранено")
            elif save_media_enabled and has_expiring_media_hint(message) and not (
                getattr(message, "voice", None) or getattr(message, "audio", None)
            ):
                unavailable_notice = (row, media)

            reply_notice = await _save_replied_media_if_owner_reply(session, message, bot, settings, values)
            if reply_notice:
                row_reply, media_reply, title_reply, downloaded = reply_notice
                if downloaded:
                    saved_notice = (row_reply, media_reply, title_reply)
                else:
                    unavailable_notice = (row_reply, media_reply)

        dot_handled = await handle_business_dot_command(
            session,
            message=message,
            bot=bot,
            settings=settings,
        )
        if dot_handled:
            await session.commit()
            return

        if not save_mode_enabled:
            await session.commit()
            return

        if row and await _handle_hard_mute_if_needed(session, message, row, media, bot, settings):
            await session.commit()
            return

        await session.commit()

    if saved_notice:
        row_saved, media_saved, title_saved = saved_notice
        await notify_business_media_saved(bot, settings, row_saved, media_saved, title=title_saved)
    elif unavailable_notice:
        row_missing, media_missing = unavailable_notice
        await notify_business_media_unavailable(bot, settings, row_missing, media_missing)


@router.edited_business_message()
async def on_edited_business_message(message: Message, bot: Bot, settings: Settings) -> None:
    async with get_session() as session:
        if not await _connection_allowed(session, message.business_connection_id, settings):
            return
        values = await get_all_settings(session)
        if not values.get("save_mode_enabled", True):
            return
        media = await download_business_media(bot, message, settings) if values.get("save_media_enabled", True) else None
        row, _, old_text = await save_business_edit(session, message, media, owner_id=settings.owner_telegram_id)
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


async def _handle_hard_mute_if_needed(session, message: Message, row, media, bot: Bot, settings: Settings) -> bool:
    sender = message.from_user
    if sender and sender.id == settings.owner_telegram_id:
        return False
    if not settings.enable_hard_mute:
        return False
    chat_type = str(getattr(message.chat, "type", ""))
    if chat_type == "channel":
        return False
    if chat_type in {"group", "supergroup"} and not settings.enable_group_hard_mute:
        return False

    chat_setting = await get_chat_setting(session, message.chat.id)
    if not hard_mute_active(chat_setting):
        return False

    event = await create_hard_mute_event(
        session,
        chat_id=message.chat.id,
        message_id=message.message_id,
        sender_id=getattr(row, "sender_id", None),
        sender_name=getattr(row, "sender_name", None),
        sender_username=getattr(row, "sender_username", None),
        text=getattr(row, "text", None) or getattr(row, "caption", None),
        media_file_id=getattr(media, "file_id", None),
        media_local_path=getattr(media, "local_path", None),
        raw_json=message.model_dump_json(exclude_none=True),
    )

    await _notify_hard_mute_hidden(bot, settings, row)

    delete_for_everyone_success = False
    delete_local_success = False
    delete_error = None
    try:
        if message.business_connection_id:
            await delete_business_messages(
                bot,
                business_connection_id=message.business_connection_id,
                message_ids=[message.message_id],
            )
            delete_for_everyone_success = True
            delete_local_success = True
        else:
            delete_error = "missing business_connection_id"
    except Exception as exc:
        delete_error = str(exc).replace("\n", " ")[:240]
        logger.warning("hard mute delete failed chat=%s msg=%s err=%s", message.chat.id, message.message_id, delete_error)
        await bot.send_message(
            settings.owner_telegram_id,
            f"Удаление для всех не удалось: {delete_error}",
        )

    await update_hard_mute_delete_status(
        session,
        event,
        delete_for_everyone_success=delete_for_everyone_success,
        delete_local_success=delete_local_success,
        delete_error=delete_error,
    )
    return True


async def _notify_hard_mute_hidden(bot: Bot, settings: Settings, row) -> None:
    chat_label = getattr(row, "chat_title", None) or str(getattr(row, "chat_id", "-"))
    author = getattr(row, "sender_name", None) or getattr(row, "sender_username", None) or str(getattr(row, "sender_id", "-"))
    text = getattr(row, "text", None) or getattr(row, "caption", None) or "[медиа без текста]"
    await bot.send_message(
        settings.owner_telegram_id,
        "🔇 Hard mute: сообщение скрыто\n\n"
        f"Чат: {chat_label}\n"
        f"Автор: {author}\n"
        f"Время: {getattr(row, 'date', '-')}\n\n"
        f"{text[:900]}",
    )


async def _save_replied_media_if_owner_reply(session, message: Message, bot: Bot, settings: Settings, values: dict):
    if not values.get("save_media_enabled", True):
        return None
    if not message.from_user or message.from_user.id != settings.owner_telegram_id:
        return None
    reply = message.reply_to_message
    if reply is None:
        return None

    has_any_media = any(
        getattr(reply, attr, None)
        for attr in ("photo", "video", "animation", "voice", "audio", "document", "video_note", "sticker")
    )
    if not has_any_media:
        return None

    message_text = (message.text or message.caption or "").strip().lower()
    by_trigger = bool(re.fullmatch(r"(?:/save|\.save|save|сохрани|\.сейв|/сейв)", message_text))
    if not by_trigger and not has_expiring_media_hint(reply):
        return None

    media = await download_business_media(bot, reply, settings, allow_voice_audio=True)
    if not media.media_type:
        return None
    row = await save_business_message(session, reply, media, owner_id=settings.owner_telegram_id)
    if media.local_path:
        return row, media, "🕒 Скрытое медиа из ответа сохранено", True
    return row, media, "⏳ Скрытое медиа из ответа обнаружено", False

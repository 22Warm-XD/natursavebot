from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import FSInputFile
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.custom import Message as TgMessage

from src.config import Settings
from src.db.repositories.chat_settings import get_chat_setting, hard_mute_active
from src.db.repositories.chats import get_chat_by_id, upsert_chat
from src.db.repositories.hard_mute import create_hard_mute_event, update_hard_mute_delete_status
from src.db.repositories.messages import upsert_message
from src.db.repositories.settings import get_all_settings
from src.db.session import get_session
from src.services.auto_reply import AutoReplyGate, build_auto_reply
from src.services.hard_mute import HardMuteDeleteResult, delete_hard_muted_message
from src.services.llm.router import LLMRouter
from src.services.save_mode import record_delete, record_edit, record_media_unavailable
from src.userbot.media import save_media_if_available
from src.utils.text import clip, html_quote


logger = logging.getLogger(__name__)
EKB_TZ = ZoneInfo("Asia/Yekaterinburg")


def attach_event_handlers(client: TelegramClient, bot: Bot, settings: Settings, llm: LLMRouter, owner_id: int) -> None:
    auto_gate = AutoReplyGate()

    @client.on(events.NewMessage())
    async def on_new_message(event: events.NewMessage.Event) -> None:
        hard_notice = None
        try:
            msg: TgMessage = event.message
            if msg.chat_id is None:
                return
            chat = await event.get_chat()
            sender = await event.get_sender()
            chat_title = _chat_title(chat) or str(msg.chat_id)
            chat_type = _chat_type(chat)
            is_private = chat_type == "private"
            sender_name = _sender_name(sender)
            sender_username = getattr(sender, "username", None)

            async with get_session() as session:
                app_settings = await get_all_settings(session)
                existing_chat = await get_chat_by_id(session, msg.chat_id)
                chat_setting = await get_chat_setting(session, msg.chat_id)
                is_hard_muted = (
                    settings.enable_hard_mute
                    and not msg.out
                    and hard_mute_active(chat_setting)
                    and (is_private or (chat_type == "group" and settings.enable_group_hard_mute))
                )
                await upsert_chat(
                    session,
                    chat_id=msg.chat_id,
                    title=chat_title,
                    username=getattr(chat, "username", None),
                    chat_type=chat_type,
                    is_bot=bool(getattr(chat, "bot", False)),
                )
                if existing_chat and existing_chat.muted_project and not is_hard_muted:
                    await session.commit()
                    return

                save_mode_allowed = _save_mode_allowed(app_settings, existing_chat, is_private)
                media_result = None
                if not msg.out and (save_mode_allowed or is_hard_muted) and app_settings.get("save_media_enabled", True):
                    media_result = await save_media_if_available(msg, settings)
                    if media_result.media_type and media_result.status in {"protected", "unavailable"}:
                        await record_media_unavailable(
                            session,
                            chat_id=msg.chat_id,
                            message_id=msg.id,
                            sender_id=msg.sender_id,
                            sender_name=sender_name,
                            media_type=media_result.media_type,
                            status=media_result.status or "unavailable",
                        )

                await upsert_message(
                    session,
                    chat_id=msg.chat_id,
                    message_id=msg.id,
                    sender_id=msg.sender_id,
                    sender_name=sender_name,
                    sender_username=sender_username,
                    chat_title=chat_title,
                    direction="outgoing" if msg.out else "incoming",
                    text_value=msg.text or msg.message or None,
                    date=msg.date.replace(tzinfo=None) if msg.date else datetime.now(UTC).replace(tzinfo=None),
                    reply_to=getattr(msg.reply_to, "reply_to_msg_id", None),
                    media_type=media_result.media_type if media_result else None,
                    media_path=media_result.path if media_result else None,
                    media_status=media_result.status if media_result else None,
                    media_meta=media_result.metadata if media_result else None,
                )
                if is_hard_muted:
                    hard_event = await create_hard_mute_event(
                        session,
                        chat_id=msg.chat_id,
                        message_id=msg.id,
                        sender_id=msg.sender_id,
                        sender_name=sender_name,
                        sender_username=sender_username,
                        text=msg.text or msg.message or None,
                        media_file_id=None,
                        media_local_path=media_result.path if media_result else None,
                        raw_json=json.dumps(msg.to_dict(), ensure_ascii=False, default=str),
                    )
                    delete_result = await delete_hard_muted_message(
                        client,
                        chat_id=msg.chat_id,
                        message_id=msg.id,
                        delete_for_everyone=bool(
                            settings.hard_mute_delete_for_everyone
                            and (chat_setting.hard_mute_delete_for_everyone if chat_setting else True)
                        ),
                    )
                    await update_hard_mute_delete_status(
                        session,
                        hard_event,
                        delete_for_everyone_success=delete_result.delete_for_everyone_success,
                        delete_local_success=delete_result.delete_local_success,
                        delete_error=delete_result.delete_error,
                    )
                    hard_notice = (hard_event, media_result, chat_title, delete_result)
                await session.commit()

            if hard_notice:
                hard_event, notice_media, notice_chat_title, delete_result = hard_notice
                await _notify_hard_mute(bot, owner_id, hard_event, notice_media, notice_chat_title, delete_result)
                return
            if not msg.out and is_private:
                await _maybe_auto_reply(client, msg, sender, settings, llm, auto_gate)
        except FloodWaitError as exc:
            logger.warning("FloodWait in new message handler: %s", exc.seconds)
        except Exception:
            logger.exception("new message handler failed")

    @client.on(events.MessageEdited())
    async def on_edit(event: events.MessageEdited.Event) -> None:
        try:
            msg: TgMessage = event.message
            if msg.chat_id is None:
                return
            async with get_session() as session:
                app_settings = await get_all_settings(session)
                chat_row = await get_chat_by_id(session, msg.chat_id)
                if not _save_mode_allowed(app_settings, chat_row, chat_row.chat_type == "private" if chat_row else False):
                    return
                note = await record_edit(
                    session,
                    chat_id=msg.chat_id,
                    message_id=msg.id,
                    new_text=msg.text or msg.message or None,
                    edited_at=datetime.now(UTC).replace(tzinfo=None),
                )
                await session.commit()
            if note and app_settings.get("save_mode_enabled", True) and app_settings.get("save_mode_notify_edits", True):
                await bot.send_message(
                    owner_id,
                    "<b>SAVE MODE: edit</b>\n"
                    f"Chat: <code>{note.event.chat_id}</code>\n"
                    f"Author: {html_quote(note.event.sender_name or '-')}\n"
                    f"<b>Было:</b> {html_quote(clip(note.event.old_text, 900))}\n"
                    f"<b>Стало:</b> {html_quote(clip(note.event.new_text, 900))}",
                )
        except Exception:
            logger.exception("edit handler failed")

    @client.on(events.MessageDeleted())
    async def on_delete(event: events.MessageDeleted.Event) -> None:
        try:
            async with get_session() as session:
                app_settings = await get_all_settings(session)
                if not app_settings.get("save_mode_enabled", True):
                    return
                chat_row = await get_chat_by_id(session, event.chat_id) if event.chat_id is not None else None
                if event.chat_id is not None and not _save_mode_allowed(app_settings, chat_row, chat_row.chat_type == "private" if chat_row else False):
                    return
                if event.chat_id is None:
                    logger.info("skip unresolved delete event without chat_id; deleted_ids=%s", list(event.deleted_ids))
                    return
                notes = await record_delete(
                    session,
                    message_ids=list(event.deleted_ids),
                    chat_id=event.chat_id,
                    deleted_at=datetime.now(UTC).replace(tzinfo=None),
                )
                await session.commit()
            if app_settings.get("save_mode_enabled", True) and app_settings.get("save_mode_notify_deletes", True):
                for note in notes:
                    await bot.send_message(
                        owner_id,
                        "<b>SAVE MODE: deleted</b>\n"
                        f"Chat: <code>{note.event.chat_id}</code>\n"
                        f"Author: {html_quote(note.event.sender_name or '-')}\n"
                        f"Text: {html_quote(clip(note.event.text, 1200))}\n"
                        f"Media: <code>{note.event.media_status or '-'}</code>",
                    )
                    if note.event.media_path and Path(note.event.media_path).exists():
                        await bot.send_document(owner_id, FSInputFile(note.event.media_path))
        except Exception:
            logger.exception("delete handler failed")


async def _maybe_auto_reply(client: TelegramClient, msg: TgMessage, sender, settings: Settings, llm: LLMRouter, gate: AutoReplyGate) -> None:
    if getattr(sender, "bot", False):
        return
    async with get_session() as session:
        app_settings = await get_all_settings(session)
        chat_row = await get_chat_by_id(session, msg.chat_id)
    if not app_settings.get("auto_reply_enabled", False):
        return
    if chat_row and (chat_row.blacklisted or chat_row.muted_project):
        return
    if app_settings.get("auto_reply_require_whitelist", True) and not (chat_row and chat_row.whitelisted):
        return
    if not gate.allowed(msg.chat_id, int(app_settings.get("auto_reply_cooldown_seconds", settings.auto_reply_cooldown_seconds))):
        return
    reply = await build_auto_reply(
        str(app_settings.get("auto_reply_mode", "static")),
        str(app_settings.get("auto_reply_text", settings.auto_reply_text)),
        msg.text or "",
        llm,
    )
    await client.send_message(msg.chat_id, reply)


async def _notify_hard_mute(
    bot: Bot,
    owner_id: int,
    hard_event,
    media_result,
    chat_title: str,
    delete_result: HardMuteDeleteResult,
) -> None:
    text = hard_event.text or "[медиа без текста]"
    body = (
        "<b>🔇 Hard mute: сообщение скрыто</b>\n\n"
        f"Чат: {html_quote(chat_title)}\n"
        f"Автор: {html_quote(hard_event.sender_name or hard_event.sender_username or str(hard_event.sender_id or '-'))}\n"
        f"Время: <code>{_format_local(hard_event.created_at)}</code>\n\n"
        f"<blockquote>{html_quote(clip(text, 900))}</blockquote>"
    )
    if not delete_result.delete_for_everyone_success and delete_result.delete_error:
        body += f"\n\nУдаление для всех не удалось: <code>{html_quote(delete_result.delete_error)}</code>"
    media_path = getattr(media_result, "path", None) if media_result else None
    media_type = getattr(media_result, "media_type", None) if media_result else None
    if media_path and Path(media_path).exists():
        await _send_hard_mute_media(bot, owner_id, media_type, media_path, body)
        return
    await bot.send_message(owner_id, body)


async def _send_hard_mute_media(bot: Bot, owner_id: int, media_type: str | None, path: str, caption: str) -> None:
    media = FSInputFile(path)
    if media_type == "photo":
        await bot.send_photo(owner_id, media, caption=caption)
    elif media_type == "video":
        await bot.send_video(owner_id, media, caption=caption)
    elif media_type == "video_note":
        await bot.send_video_note(owner_id, media)
        await bot.send_message(owner_id, caption)
    elif media_type == "sticker":
        await bot.send_sticker(owner_id, media)
        await bot.send_message(owner_id, caption)
    else:
        await bot.send_document(owner_id, media, caption=caption)


def _format_local(value: datetime | None) -> str:
    if value is None:
        return "-"
    dt = value if value.tzinfo else value.replace(tzinfo=UTC)
    return dt.astimezone(EKB_TZ).strftime("%H:%M %d.%m.%y")


def _save_mode_allowed(app_settings: dict, chat_row, is_private: bool) -> bool:
    if not app_settings.get("save_mode_enabled", True):
        return False
    if chat_row and (chat_row.blacklisted or chat_row.muted_project):
        return False
    return _scope_allows(str(app_settings.get("save_mode_scope", "private")), is_private)


def _scope_allows(scope: str, is_private: bool) -> bool:
    return is_private or scope == "private_and_groups"


def _chat_title(chat) -> str | None:
    title = getattr(chat, "title", None)
    if title:
        return title
    parts = [getattr(chat, "first_name", None), getattr(chat, "last_name", None)]
    return " ".join(part for part in parts if part).strip() or getattr(chat, "username", None)


def _sender_name(sender) -> str | None:
    if sender is None:
        return None
    parts = [getattr(sender, "first_name", None), getattr(sender, "last_name", None)]
    return " ".join(part for part in parts if part).strip() or getattr(sender, "username", None) or str(getattr(sender, "id", ""))


def _chat_type(chat) -> str:
    if getattr(chat, "bot", False) is not None and hasattr(chat, "first_name"):
        return "private"
    if getattr(chat, "broadcast", False):
        return "channel"
    if getattr(chat, "megagroup", False) or getattr(chat, "title", None):
        return "group"
    return "unknown"

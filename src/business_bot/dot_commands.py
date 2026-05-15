from __future__ import annotations

import asyncio
import logging
import random
import time
from types import SimpleNamespace

from aiogram import Bot
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.business_bot.sender import delete_business_messages, send_business_chat_action, send_business_message
from src.config import Settings
from src.db.repositories.chat_settings import set_hard_mute
from src.services.hard_mute import DotCommandCooldown, clamp_repeat_count, parse_repeat_args
from src.services.user_info import format_user_info


logger = logging.getLogger(__name__)
_cooldown = DotCommandCooldown()
_LOVE_FRAMES = ["✨❤️", "❤️‍🔥❤️", "💫❤️‍🔥💫", "❤️❤️❤️", "✨❤️✨"]
_repeat_tasks: dict[int, asyncio.Task] = {}

_DOT_ALIASES = {
    ".мут": ".mute",
    ".размут": ".unmute",
    ".тайп": ".type",
    ".спам": ".spam",
    ".репит": ".repeat",
    ".стопспам": ".spam_stop",
    ".stopspam": ".spam_stop",
    ".лав": ".love",
    ".инфо": ".info",
}


async def handle_business_dot_command(
    session: AsyncSession,
    *,
    message: Message,
    bot: Bot,
    settings: Settings,
) -> bool:
    if not settings.enable_dot_commands:
        return False
    if not message.from_user or message.from_user.id != settings.owner_telegram_id:
        return False
    full_text = (message.text or message.caption or "").strip()
    if not full_text.startswith("."):
        return False

    command_raw, _, _ = full_text.partition(" ")
    body = full_text[len(command_raw) :].strip()
    command = _DOT_ALIASES.get(command_raw.lower(), command_raw.lower())
    if command not in {".mute", ".unmute", ".type", ".spam", ".repeat", ".spam_stop", ".love", ".info"}:
        return False

    connection_id = message.business_connection_id
    if not connection_id:
        logger.error("business dot command without business_connection_id command=%s chat_id=%s", command, message.chat.id)
        await _safe_owner_error(bot, settings, f"{command}: отсутствует business_connection_id, команда не выполнена.")
        return True

    chat_type = str(getattr(message.chat, "type", ""))
    if _is_group_chat(chat_type) and not settings.enable_group_dot_commands:
        return True

    if command == ".mute":
        await _cmd_mute(session, message, bot, settings, connection_id)
    elif command == ".unmute":
        await _cmd_unmute(session, message, bot, settings, connection_id)
    elif command == ".type":
        await _cmd_type(message, bot, settings, connection_id, body)
    elif command in {".spam", ".repeat"}:
        await _cmd_repeat(message, bot, settings, connection_id, command, body, chat_type)
    elif command == ".spam_stop":
        await _cmd_repeat_stop(message.chat.id)
    elif command == ".love":
        await _cmd_love(message, bot, settings, connection_id)
    elif command == ".info":
        await _cmd_info(message, bot, connection_id)

    await _try_delete_command_message(bot, connection_id, message.message_id)
    return True


async def _cmd_mute(
    session: AsyncSession,
    message: Message,
    bot: Bot,
    settings: Settings,
    connection_id: str,
) -> None:
    await set_hard_mute(
        session,
        chat_id=message.chat.id,
        enabled=True,
        chat_title=_chat_title(message),
        username=getattr(message.chat, "username", None),
        delete_for_everyone=settings.hard_mute_delete_for_everyone,
    )
    await send_business_message(
        bot,
        business_connection_id=connection_id,
        chat_id=message.chat.id,
        text="🔇 Hard mute включён.",
    )


async def _cmd_unmute(
    session: AsyncSession,
    message: Message,
    bot: Bot,
    settings: Settings,
    connection_id: str,
) -> None:
    await set_hard_mute(
        session,
        chat_id=message.chat.id,
        enabled=False,
        chat_title=_chat_title(message),
        username=getattr(message.chat, "username", None),
        delete_for_everyone=settings.hard_mute_delete_for_everyone,
    )
    await send_business_message(
        bot,
        business_connection_id=connection_id,
        chat_id=message.chat.id,
        text="🔔 Hard mute выключен.",
    )


async def _cmd_type(
    message: Message,
    bot: Bot,
    settings: Settings,
    connection_id: str,
    text: str,
) -> None:
    if not text:
        return
    text = text[: settings.type_max_text_length]
    try:
        await send_business_chat_action(
            bot,
            business_connection_id=connection_id,
            chat_id=message.chat.id,
            action="typing",
        )
    except Exception:
        logger.debug("business typing action failed", exc_info=True)
    await asyncio.sleep(min(3.0, max(0.35, len(text) / 45)))
    try:
        await send_business_message(
            bot,
            business_connection_id=connection_id,
            chat_id=message.chat.id,
            text=text,
        )
    except Exception:
        logger.exception("business .type send failed chat_id=%s", message.chat.id)


async def _cmd_repeat(
    message: Message,
    bot: Bot,
    settings: Settings,
    connection_id: str,
    command: str,
    raw_args: str,
    chat_type: str,
) -> None:
    if command == ".spam" and not settings.enable_spam_alias:
        return
    if _is_group_chat(chat_type) and not settings.enable_group_repeat:
        return
    left = _cooldown.check(
        settings.owner_telegram_id,
        "repeat",
        time.monotonic(),
        settings.dot_command_cooldown_seconds,
    )
    if left > 0:
        return
    count_raw, text = parse_repeat_args(raw_args)
    if count_raw is None or text is None:
        return
    count, clamped = clamp_repeat_count(count_raw, settings)
    if clamped:
        logger.info("repeat count clamped chat_id=%s requested=%s actual=%s", message.chat.id, count_raw, count)
    text = text[: settings.type_max_text_length]
    await _cmd_repeat_stop(message.chat.id)
    _repeat_tasks[message.chat.id] = asyncio.create_task(
        _repeat_worker(
            bot=bot,
            business_connection_id=connection_id,
            chat_id=message.chat.id,
            text=text,
            count=count,
            min_delay=max(0.1, float(settings.repeat_delay_min_seconds)),
            max_delay=max(float(settings.repeat_delay_min_seconds), float(settings.repeat_delay_max_seconds)),
        )
    )


async def _cmd_love(message: Message, bot: Bot, settings: Settings, connection_id: str) -> None:
    left = _cooldown.check(
        settings.owner_telegram_id,
        "love",
        time.monotonic(),
        settings.dot_command_cooldown_seconds,
    )
    if left > 0:
        return
    frames = _LOVE_FRAMES[: max(1, min(int(settings.love_animation_max_messages), 5))]
    for frame in frames:
        await send_business_message(
            bot,
            business_connection_id=connection_id,
            chat_id=message.chat.id,
            text=frame,
        )
        await asyncio.sleep(0.7)


async def _cmd_info(message: Message, bot: Bot, connection_id: str) -> None:
    reply = message.reply_to_message
    target_id = None
    user = None
    if reply is not None:
        target_id = getattr(reply, "message_id", None)
        reply_user = getattr(reply, "from_user", None)
        if reply_user:
            user = _user_from_aiogram(reply_user)
    elif str(getattr(message.chat, "type", "")) == "private":
        target_id = message.message_id
        user = _user_from_private_chat(message)

    if user is None:
        return

    text = format_user_info(
        user,
        chat_id=message.chat.id,
        message_id=target_id,
        common_chats_count=None,
        profile_photo_count=None,
    )
    await send_business_message(
        bot,
        business_connection_id=connection_id,
        chat_id=message.chat.id,
        text=text,
        reply_to_message_id=target_id,
        parse_mode="HTML",
    )


async def _try_delete_command_message(bot: Bot, connection_id: str, message_id: int) -> None:
    try:
        await delete_business_messages(
            bot,
            business_connection_id=connection_id,
            message_ids=[message_id],
        )
    except Exception:
        logger.debug("failed to delete dot command message id=%s", message_id, exc_info=True)


async def _repeat_worker(
    *,
    bot: Bot,
    business_connection_id: str,
    chat_id: int,
    text: str,
    count: int,
    min_delay: float,
    max_delay: float,
) -> None:
    try:
        for _ in range(count):
            await send_business_message(
                bot,
                business_connection_id=business_connection_id,
                chat_id=chat_id,
                text=text,
            )
            await asyncio.sleep(random.uniform(min_delay, max_delay))
    except asyncio.CancelledError:
        logger.info("repeat task cancelled chat_id=%s", chat_id)
        raise
    except Exception:
        logger.exception("repeat worker failed chat_id=%s", chat_id)
    finally:
        current = _repeat_tasks.get(chat_id)
        if current and current.done():
            _repeat_tasks.pop(chat_id, None)


async def _cmd_repeat_stop(chat_id: int) -> None:
    task = _repeat_tasks.pop(chat_id, None)
    if not task:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def _is_group_chat(chat_type: str) -> bool:
    return chat_type in {"group", "supergroup", "channel"}


def _chat_title(message: Message) -> str:
    return (
        getattr(message.chat, "title", None)
        or getattr(message.chat, "full_name", None)
        or getattr(message.chat, "username", None)
        or str(message.chat.id)
    )


def _user_from_aiogram(user) -> SimpleNamespace:
    return SimpleNamespace(
        id=getattr(user, "id", None),
        username=getattr(user, "username", None),
        first_name=getattr(user, "first_name", None),
        last_name=getattr(user, "last_name", None),
        bot=getattr(user, "is_bot", False),
        premium=getattr(user, "is_premium", None),
        verified=getattr(user, "is_verified", False),
        scam=getattr(user, "is_scam", False),
        fake=getattr(user, "is_fake", False),
        restricted=getattr(user, "is_restricted", False),
        lang_code=getattr(user, "language_code", None),
        mutual_contact=getattr(user, "is_mutual_contact", None),
        phone=None,
        access_hash=None,
        status=None,
    )


def _user_from_private_chat(message: Message) -> SimpleNamespace:
    chat = message.chat
    return SimpleNamespace(
        id=getattr(chat, "id", None),
        username=getattr(chat, "username", None),
        first_name=getattr(chat, "first_name", None),
        last_name=getattr(chat, "last_name", None),
        bot=False,
        premium=None,
        verified=False,
        scam=False,
        fake=False,
        restricted=False,
        lang_code=None,
        mutual_contact=None,
        phone=None,
        access_hash=None,
        status=None,
    )


async def _safe_owner_error(bot: Bot, settings: Settings, text: str) -> None:
    try:
        await bot.send_message(chat_id=settings.owner_telegram_id, text=text)
    except Exception:
        logger.warning("failed to notify owner about business dot command error", exc_info=True)

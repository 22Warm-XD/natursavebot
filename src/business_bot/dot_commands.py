from __future__ import annotations

import asyncio
import logging
import time
from types import SimpleNamespace

from aiogram import Bot
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.business_bot.sender import delete_business_messages, send_business_chat_action, send_business_message
from src.config import Settings
from src.db.repositories.chat_settings import set_hard_mute
from src.services.hard_mute import DotCommandCooldown, clamp_repeat_count, dot_usage, parse_repeat_args
from src.services.user_info import format_user_info


logger = logging.getLogger(__name__)
_cooldown = DotCommandCooldown()
_LOVE_FRAMES = ["❤️", "❤️❤️", "❤️❤️❤️", "❤️❤️", "❤️"]
_DOT_ALIASES = {
    ".мут": ".mute",
    ".размут": ".unmute",
    ".тайп": ".type",
    ".спам": ".spam",
    ".репит": ".repeat",
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
    text = (message.text or message.caption or "").strip()
    if not text.startswith("."):
        return False
    command_raw, _, rest = text.partition(" ")
    command = _DOT_ALIASES.get(command_raw.lower(), command_raw.lower())
    if command not in {".mute", ".unmute", ".type", ".spam", ".repeat", ".love", ".info"}:
        return False

    connection_id = message.business_connection_id
    if not connection_id:
        logger.error("business dot command without business_connection_id command=%s chat_id=%s", command, message.chat.id)
        await _safe_owner_error(bot, settings, f"{command}: отсутствует business_connection_id, команда не выполнена.")
        return True

    chat_type = str(getattr(message.chat, "type", ""))
    if _is_group_chat(chat_type) and not settings.enable_group_dot_commands:
        await send_business_message(
            bot,
            business_connection_id=connection_id,
            chat_id=message.chat.id,
            text=f"{command}: отключено для групп. Включи ENABLE_GROUP_DOT_COMMANDS=true, если нужно.",
            reply_to_message_id=message.message_id,
        )
        return True

    if command == ".mute":
        await _cmd_mute(session, message, bot, settings, connection_id)
    elif command == ".unmute":
        await _cmd_unmute(session, message, bot, settings, connection_id)
    elif command == ".type":
        await _cmd_type(message, bot, settings, connection_id, rest.strip())
    elif command in {".spam", ".repeat"}:
        await _cmd_repeat(message, bot, settings, connection_id, command, rest.strip(), chat_type)
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
        await send_business_message(
            bot,
            business_connection_id=connection_id,
            chat_id=message.chat.id,
            text=dot_usage(".type"),
            reply_to_message_id=message.message_id,
        )
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
    await send_business_message(
        bot,
        business_connection_id=connection_id,
        chat_id=message.chat.id,
        text=text,
    )


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
        await send_business_message(
            bot,
            business_connection_id=connection_id,
            chat_id=message.chat.id,
            text="Используй .repeat. Alias .spam выключен.",
            reply_to_message_id=message.message_id,
        )
        return
    if _is_group_chat(chat_type) and not settings.enable_group_repeat:
        await send_business_message(
            bot,
            business_connection_id=connection_id,
            chat_id=message.chat.id,
            text="Повтор в группах выключен. Включи ENABLE_GROUP_REPEAT=true, если нужно.",
            reply_to_message_id=message.message_id,
        )
        return
    left = _cooldown.check(
        settings.owner_telegram_id,
        "repeat",
        time.monotonic(),
        settings.dot_command_cooldown_seconds,
    )
    if left > 0:
        await send_business_message(
            bot,
            business_connection_id=connection_id,
            chat_id=message.chat.id,
            text=f"Cooldown: подожди ещё {int(left) + 1} сек.",
            reply_to_message_id=message.message_id,
        )
        return
    count_raw, text = parse_repeat_args(raw_args)
    if count_raw is None or text is None:
        await send_business_message(
            bot,
            business_connection_id=connection_id,
            chat_id=message.chat.id,
            text=dot_usage(command),
            reply_to_message_id=message.message_id,
        )
        return
    count, clamped = clamp_repeat_count(count_raw, settings)
    text = text[: settings.type_max_text_length]
    if clamped:
        await send_business_message(
            bot,
            business_connection_id=connection_id,
            chat_id=message.chat.id,
            text=f"Лимит повтора: {count}. Отправляю только разрешённое количество.",
        )
    for _ in range(count):
        await send_business_message(
            bot,
            business_connection_id=connection_id,
            chat_id=message.chat.id,
            text=text,
        )
        await asyncio.sleep(max(float(settings.repeat_delay_seconds), 0.1))


async def _cmd_love(message: Message, bot: Bot, settings: Settings, connection_id: str) -> None:
    left = _cooldown.check(
        settings.owner_telegram_id,
        "love",
        time.monotonic(),
        settings.dot_command_cooldown_seconds,
    )
    if left > 0:
        await send_business_message(
            bot,
            business_connection_id=connection_id,
            chat_id=message.chat.id,
            text=f"Cooldown: подожди ещё {int(left) + 1} сек.",
            reply_to_message_id=message.message_id,
        )
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
        await send_business_message(
            bot,
            business_connection_id=connection_id,
            chat_id=message.chat.id,
            text="Ответь командой .info на сообщение пользователя.",
            reply_to_message_id=message.message_id,
        )
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

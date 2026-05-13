from __future__ import annotations

import asyncio
import logging
import time

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import GetCommonChatsRequest

from src.config import Settings
from src.db.repositories.chat_settings import set_hard_mute
from src.db.repositories.chats import upsert_chat
from src.db.session import get_session
from src.services.hard_mute import DotCommandCooldown, clamp_repeat_count, dot_usage, parse_repeat_args
from src.services.user_info import format_user_info


logger = logging.getLogger(__name__)
_cooldown = DotCommandCooldown()
_LOVE_FRAMES = ["❤️", "❤️❤️", "❤️❤️❤️", "❤️❤️", "❤️"]


def attach_user_commands(client: TelegramClient, owner_id: int, settings: Settings) -> None:
    own_id_cache: dict[str, int] = {}

    async def is_owner(event: events.NewMessage.Event) -> bool:
        if not settings.enable_dot_commands or not event.out or not owner_id:
            return False
        sender_id = event.sender_id
        if sender_id is None:
            if "id" not in own_id_cache:
                me = await client.get_me()
                own_id_cache["id"] = int(me.id)
            sender_id = own_id_cache["id"]
        return int(sender_id) == int(owner_id)

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.mute$"))
    async def mute(event: events.NewMessage.Event) -> None:
        if not await is_owner(event):
            return
        if not settings.enable_hard_mute:
            await event.edit("Hard mute выключен в настройках проекта.")
            return
        chat, chat_title, username, chat_type = await _chat_meta(event)
        if chat_type != "private" and not settings.enable_group_hard_mute:
            await event.edit("Hard mute в группах выключен. Включи ENABLE_GROUP_HARD_MUTE=true, если это точно нужно.")
            return
        async with get_session() as session:
            await upsert_chat(
                session,
                chat_id=event.chat_id,
                title=chat_title,
                username=username,
                chat_type=chat_type,
                is_bot=bool(getattr(chat, "bot", False)),
            )
            await set_hard_mute(
                session,
                chat_id=event.chat_id,
                enabled=True,
                chat_title=chat_title,
                username=username,
                delete_for_everyone=settings.hard_mute_delete_for_everyone,
            )
            await session.commit()
        await event.edit(
            "🔇 Hard mute включён. Новые сообщения из этого чата будут сохраняться в Mnemora "
            "и удаляться из переписки, если Telegram позволит."
        )

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.unmute$"))
    async def unmute(event: events.NewMessage.Event) -> None:
        if not await is_owner(event):
            return
        chat, chat_title, username, _ = await _chat_meta(event)
        async with get_session() as session:
            await set_hard_mute(
                session,
                chat_id=event.chat_id,
                enabled=False,
                chat_title=chat_title,
                username=username,
                delete_for_everyone=settings.hard_mute_delete_for_everyone,
            )
            await session.commit()
        await event.edit("🔔 Hard mute выключен. Новые сообщения из этого чата больше не будут удаляться автоматически.")

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.info$"))
    async def info(event: events.NewMessage.Event) -> None:
        if not await is_owner(event):
            return
        reply = await event.get_reply_message()
        target_message_id = getattr(reply, "id", None)
        try:
            if reply is not None and getattr(reply, "sender_id", None) is not None:
                user = await reply.get_sender() or await client.get_entity(reply.sender_id)
            elif event.is_private:
                user = await event.get_chat()
                target_message_id = event.id
            else:
                await event.edit("Ответь командой .info на сообщение пользователя.")
                return

            common_chats_count = await _common_chats_count(client, user)
            profile_photo_count = await _profile_photo_count(client, user)
            text = format_user_info(
                user,
                chat_id=event.chat_id,
                message_id=target_message_id,
                common_chats_count=common_chats_count,
                profile_photo_count=profile_photo_count,
            )
            try:
                await event.delete()
            except Exception:
                logger.debug("failed to delete .info command", exc_info=True)
            await client.send_message(
                event.chat_id,
                text,
                reply_to=target_message_id,
                parse_mode="html",
            )
        except Exception:
            logger.exception(".info failed")
            await event.edit("Не удалось получить информацию о пользователе.")

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.type(?:\s+(.+))?$"))
    async def type_text(event: events.NewMessage.Event) -> None:
        if not await is_owner(event):
            return
        text = (event.pattern_match.group(1) or "").strip()
        if not text:
            await event.edit(dot_usage(".type"))
            return
        text = text[: settings.type_max_text_length]
        try:
            async with client.action(event.chat_id, "typing"):
                await asyncio.sleep(min(3.0, max(0.35, len(text) / 45)))
            await event.delete()
            await client.send_message(event.chat_id, text)
        except FloodWaitError as exc:
            await asyncio.sleep(exc.seconds)
        except Exception:
            logger.exception(".type failed")

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.(spam|repeat)(?:\s+(.+))?$"))
    async def repeat(event: events.NewMessage.Event) -> None:
        if not await is_owner(event):
            return
        command = "." + event.pattern_match.group(1).lower()
        if command == ".spam" and not settings.enable_spam_alias:
            await event.edit("Используй .repeat. Alias .spam выключен в настройках.")
            return
        _, _, _, chat_type = await _chat_meta(event)
        if chat_type != "private" and not settings.enable_group_repeat:
            await event.edit("Повтор в группах выключен. Включи ENABLE_GROUP_REPEAT=true, если это точно нужно.")
            return
        left = _cooldown.check(owner_id, "repeat", time.monotonic(), settings.dot_command_cooldown_seconds)
        if left > 0:
            await event.edit(f"Cooldown: подожди ещё {int(left) + 1} сек.")
            return
        count_raw, text = parse_repeat_args(event.pattern_match.group(2))
        if count_raw is None or text is None:
            await event.edit(dot_usage(command))
            return
        count, clamped = clamp_repeat_count(count_raw, settings)
        text = text[: settings.type_max_text_length]
        try:
            await event.delete()
        except Exception:
            logger.debug("failed to delete repeat command", exc_info=True)
        if clamped:
            await client.send_message(event.chat_id, f"Лимит повтора: {count}. Отправляю только разрешённое количество.")
        for _ in range(count):
            try:
                await client.send_message(event.chat_id, text)
            except FloodWaitError as exc:
                await asyncio.sleep(exc.seconds)
            await asyncio.sleep(max(float(settings.repeat_delay_seconds), 0.1))

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.love$"))
    async def love(event: events.NewMessage.Event) -> None:
        if not await is_owner(event):
            return
        left = _cooldown.check(owner_id, "love", time.monotonic(), settings.dot_command_cooldown_seconds)
        if left > 0:
            await event.edit(f"Cooldown: подожди ещё {int(left) + 1} сек.")
            return
        frames = _LOVE_FRAMES[: max(1, min(int(settings.love_animation_max_messages), 5))]
        try:
            await event.delete()
        except Exception:
            logger.debug("failed to delete .love command", exc_info=True)
        for frame in frames:
            await client.send_message(event.chat_id, frame)
            await asyncio.sleep(0.7)


async def _chat_meta(event: events.NewMessage.Event):
    chat = await event.get_chat()
    title = _chat_title(chat) or str(event.chat_id)
    username = getattr(chat, "username", None)
    return chat, title, username, _chat_type(chat)


def _chat_title(chat) -> str | None:
    title = getattr(chat, "title", None)
    if title:
        return title
    parts = [getattr(chat, "first_name", None), getattr(chat, "last_name", None)]
    return " ".join(part for part in parts if part).strip() or getattr(chat, "username", None)


def _chat_type(chat) -> str:
    if getattr(chat, "broadcast", False):
        return "channel"
    if getattr(chat, "megagroup", False) or getattr(chat, "title", None):
        return "group"
    if hasattr(chat, "first_name"):
        return "private"
    return "unknown"


async def _common_chats_count(client: TelegramClient, user) -> int | None:
    try:
        entity = await client.get_input_entity(user)
        result = await client(GetCommonChatsRequest(user_id=entity, max_id=0, limit=100))
        chats = getattr(result, "chats", None)
        return len(chats) if chats is not None else None
    except Exception:
        return None


async def _profile_photo_count(client: TelegramClient, user) -> int | None:
    try:
        photos = await client.get_profile_photos(user, limit=1)
        return int(getattr(photos, "total", len(photos)))
    except Exception:
        return None

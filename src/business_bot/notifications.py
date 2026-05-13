from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import FSInputFile, LinkPreviewOptions

from src.config import Settings
from src.utils.text import clip, html_quote


TRASH_EMOJI = '<tg-emoji emoji-id="5879896690210639947">🗑</tg-emoji>'
EDIT_EMOJI = '<tg-emoji emoji-id="5879841310902324730">✏️</tg-emoji>'
TIME_EMOJI = '<tg-emoji emoji-id="5778605968208170641">🕒</tg-emoji>'
PHOTO_EMOJI = '<tg-emoji emoji-id="5992441476364112370">🖼</tg-emoji>'
EFFECT_FIREWORK = "5046509860389126442"
EFFECT_THUMBS_UP = "5107584321108051014"
EFFECT_POOP = "5046589136895476101"
EFFECT_FIRE = "5104841245755180586"
EFFECT_HEART = "5159385139981059251"

MEDIA_TITLES = {
    "photo": "Фото было удалено",
    "video": "Видео было удалено",
    "animation": "GIF/анимация была удалена",
    "voice": "Голосовое было удалено",
    "audio": "Аудио было удалено",
    "document": "Файл был удалён",
    "video_note": "Видео-кружок был удалён",
    "sticker": "Стикер был удалён",
    "paid_media": "Медиа было удалено",
}
EKB_TZ = ZoneInfo("Asia/Yekaterinburg")


async def notify_business_enabled(bot: Bot, settings: Settings) -> None:
    await _safe_message(
        bot,
        settings.owner_telegram_id,
        "✅ <b>Mnemora Save Mode подключён.</b>\n\n"
        "Бот будет сохранять удалённые сообщения, правки и доступные медиа из разрешённых Telegram Business чатов.",
    )


async def notify_business_disabled(bot: Bot, settings: Settings) -> None:
    await _safe_message(
        bot,
        settings.owner_telegram_id,
        "🚫 <b>SaveMOD был отключён.</b>\n\n"
        "Если вы сделали это по просьбе незнакомого пользователя для проведения сделки, получения приза "
        "или под другим предлогом, советуем остановиться и разобраться в ситуации.\n\n"
        "Возможно, вас пытаются обмануть. Не отключайте защиту по чужой просьбе.",
    )


async def notify_business_delete(bot: Bot, settings: Settings, message, *, chat_label: str | None = None) -> None:
    title = MEDIA_TITLES.get(message.media_type) if message and message.media_type else "Это сообщение было удалено"
    marker = _media_marker(getattr(message, "media_type", None))
    body = _delete_caption(message, title=f"{marker} {title}".strip(), chat_label=chat_label)
    media_path = getattr(message, "media_path", None)
    if media_path and Path(media_path).exists():
        await _send_media_with_caption(
            bot,
            settings.owner_telegram_id,
            message.media_type,
            media_path,
            body,
            message_effect_id=EFFECT_POOP,
        )
        return
    if getattr(message, "media_type", None):
        status = html_quote(getattr(message, "media_status", None) or "unknown")
        body += f"\n\nМедиа недоступно через Bot API / protected / expired.\nStatus: <code>{status}</code>"
    await _safe_message(bot, settings.owner_telegram_id, body, message_effect_id=EFFECT_POOP)


async def notify_business_media_saved(bot: Bot, settings: Settings, message, media, *, title: str | None = None) -> None:
    media_title = title or f"{_media_marker(getattr(media, 'media_type', None))} Медиа сохранено"
    body = _media_caption(message, title=media_title, media=media)
    media_path = getattr(media, "local_path", None)
    if media_path and Path(media_path).exists():
        await _send_media_with_caption(
            bot,
            settings.owner_telegram_id,
            getattr(media, "media_type", None),
            media_path,
            body,
            message_effect_id=EFFECT_HEART,
        )
    else:
        await _safe_message(bot, settings.owner_telegram_id, body, message_effect_id=EFFECT_HEART)


async def notify_business_media_unavailable(bot: Bot, settings: Settings, message, media=None) -> None:
    status = html_quote(getattr(media, "status", None) or "unavailable")
    body = _media_caption(
        message,
        title="⏳ Истекающее медиа обнаружено",
        media=media,
        extra=f"\n\nМедиа недоступно через Bot API / protected / expired.\nStatus: <code>{status}</code>",
    )
    await _safe_message(bot, settings.owner_telegram_id, body, message_effect_id=EFFECT_HEART)


async def notify_business_delete_missing(bot: Bot, settings: Settings, *, chat_id: int, message_ids: list[int]) -> None:
    await _safe_message(
        bot,
        settings.owner_telegram_id,
        f"<b>{TRASH_EMOJI} Это сообщение было удалено</b>\n\n"
        f"Чат: <code>{chat_id}</code>\n"
        f"Message IDs: <code>{', '.join(map(str, message_ids))}</code>\n\n"
        "Содержимого нет в локальной базе. Возможно, бот был подключён после отправки сообщения "
        "или Telegram не дал доступ к этому сообщению.\n\n"
        "Сохранено Mnemora Save Mode",
    )


async def notify_business_edit(
    bot: Bot,
    settings: Settings,
    *,
    sender_name: str | None,
    sender_username: str | None = None,
    chat_label: str | None,
    chat_id: int | None = None,
    message_date=None,
    old_text: str | None,
    new_text: str | None,
) -> None:
    await _safe_message(
        bot,
        settings.owner_telegram_id,
        f"<b>{EDIT_EMOJI} {html_quote(sender_name or 'Пользователь')} отредактировал сообщение.</b>\n"
        f"{_chat_link_from_values(chat_label=chat_label, username=sender_username, chat_id=chat_id)} · {TIME_EMOJI} <code>{_format_date(message_date)}</code>\n\n"
        f"<blockquote>{html_quote(clip(old_text or '[старой версии нет в базе]', 900))}</blockquote>\n\n"
        "↓↓↓\n\n"
        f"<blockquote>{html_quote(clip(new_text or '', 900))}</blockquote>\n\n"
        "Сохранено Mnemora Save Mode",
        message_effect_id=EFFECT_FIRE,
    )


def _delete_caption(message, *, title: str, chat_label: str | None) -> str:
    text = getattr(message, "text", None) or getattr(message, "caption", None) or "[медиа без текста]"
    return (
        f"<b>{TRASH_EMOJI} {html_quote(title)}</b>\n\n"
        f"{_chat_link(message, chat_label)} · {TIME_EMOJI} <code>{_format_date(getattr(message, 'date', None))}</code>\n\n"
        f"<blockquote>{html_quote(getattr(message, 'sender_name', None) or getattr(message, 'sender_username', None) or str(getattr(message, 'sender_id', '-')))}\n{html_quote(clip(text, 650))}</blockquote>\n\n"
        "Сохранено Mnemora Save Mode"
    )


def _media_caption(message, *, title: str, media=None, extra: str = "") -> str:
    text = getattr(message, "text", None) or getattr(message, "caption", None) or "[медиа без текста]"
    return (
        f"<b>{html_quote(title)}</b>\n\n"
        f"{_chat_link(message, None)} · {TIME_EMOJI} <code>{_format_date(getattr(message, 'date', None))}</code>\n\n"
        f"<blockquote>{html_quote(clip(text, 450))}</blockquote>"
        f"{extra}\n\n"
        "Сохранено Mnemora Save Mode"
    )


async def _send_media_with_caption(
    bot: Bot,
    owner_id: int,
    media_type: str | None,
    path: str,
    caption: str,
    *,
    message_effect_id: str | None = None,
) -> None:
    media = FSInputFile(path)
    if media_type == "photo":
        await _send_with_effect_retry(bot.send_photo, owner_id, media, caption, message_effect_id)
    elif media_type == "video":
        await _send_with_effect_retry(bot.send_video, owner_id, media, caption, message_effect_id)
    elif media_type == "animation":
        await _send_with_effect_retry(bot.send_animation, owner_id, media, caption, message_effect_id)
    elif media_type == "voice":
        await _send_with_effect_retry(bot.send_voice, owner_id, media, caption, message_effect_id)
    elif media_type == "audio":
        await _send_with_effect_retry(bot.send_audio, owner_id, media, caption, message_effect_id)
    elif media_type == "video_note":
        await bot.send_video_note(owner_id, media)
        await _safe_message(bot, owner_id, caption, message_effect_id=message_effect_id)
    elif media_type == "sticker":
        await bot.send_sticker(owner_id, media)
        await _safe_message(bot, owner_id, caption, message_effect_id=message_effect_id)
    else:
        await _send_with_effect_retry(bot.send_document, owner_id, media, caption, message_effect_id)


def _media_marker(media_type: str | None) -> str:
    return {
        "photo": PHOTO_EMOJI,
        "video": "🎬",
        "animation": "🎞",
        "voice": "🎙",
        "audio": "🎧",
        "document": "📎",
        "video_note": "⭕",
        "sticker": "🏷",
    }.get(media_type, "")


def _chat_link(message, chat_label: str | None) -> str:
    label = chat_label or getattr(message, "chat_title", None) or _chat_title_from_aiogram(message) or str(getattr(message, "chat_id", "-"))
    username = _username_from_message(message)
    if username:
        safe_username = html_quote(username)
        return f'<a href="https://t.me/{safe_username}">{html_quote(label)}</a> · <code>t.me/{safe_username}</code>'
    chat_id = getattr(message, "chat_id", None) or getattr(getattr(message, "chat", None), "id", None)
    if chat_id:
        return f'<a href="tg://user?id={chat_id}">{html_quote(label)}</a>'
    return html_quote(label)


def _chat_link_from_values(*, chat_label: str | None, username: str | None, chat_id: int | None) -> str:
    label = chat_label or username or (str(chat_id) if chat_id else "чат")
    username = (username or "").lstrip("@").strip()
    if username and all(part.isalnum() or part == "_" for part in username):
        safe_username = html_quote(username)
        return f'<a href="https://t.me/{safe_username}">{html_quote(label)}</a> · <code>t.me/{safe_username}</code>'
    if chat_id:
        return f'<a href="tg://user?id={chat_id}">{html_quote(label)}</a>'
    return html_quote(label)


def _username_from_message(message) -> str | None:
    username = getattr(message, "sender_username", None)
    if not username and hasattr(message, "chat"):
        username = getattr(message.chat, "username", None)
    if not username and hasattr(message, "from_user") and message.from_user:
        username = getattr(message.from_user, "username", None)
    username = (username or "").lstrip("@").strip()
    if username and all(part.isalnum() or part == "_" for part in username):
        return username
    return None


def _chat_title_from_aiogram(message) -> str | None:
    chat = getattr(message, "chat", None)
    if chat is None:
        return None
    return (
        getattr(chat, "title", None)
        or getattr(chat, "full_name", None)
        or getattr(chat, "username", None)
    )


def _sender_name_from_aiogram(message) -> str | None:
    user = getattr(message, "from_user", None)
    if user is None:
        return None
    return " ".join(part for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if part).strip() or getattr(user, "username", None)


def _format_date(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return html_quote(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(EKB_TZ).strftime("%H:%M %d.%m.%y")


async def _send_with_effect_retry(sender, owner_id: int, media: FSInputFile, caption: str, message_effect_id: str | None) -> None:
    kwargs = {"caption": caption}
    if message_effect_id:
        kwargs["message_effect_id"] = message_effect_id
    try:
        await sender(owner_id, media, **kwargs)
    except TypeError:
        kwargs.pop("message_effect_id", None)
        await sender(owner_id, media, **kwargs)


async def _safe_message(bot: Bot, chat_id: int, text: str, *, message_effect_id: str | None = None) -> None:
    kwargs = {
        "chat_id": chat_id,
        "text": text,
        "link_preview_options": LinkPreviewOptions(is_disabled=True),
    }
    if message_effect_id:
        kwargs["message_effect_id"] = message_effect_id
    try:
        await bot.send_message(**kwargs)
    except TypeError:
        kwargs.pop("message_effect_id", None)
        await bot.send_message(**kwargs)

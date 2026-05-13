from __future__ import annotations

import html
from datetime import UTC

from telethon.tl.types import UserStatusLastMonth, UserStatusLastWeek, UserStatusOffline, UserStatusOnline, UserStatusRecently


def format_user_info(
    user,
    *,
    chat_id: int | None,
    message_id: int | None,
    common_chats_count: int | None = None,
    profile_photo_count: int | None = None,
) -> str:
    username = getattr(user, "username", None)
    first_name = getattr(user, "first_name", None)
    last_name = getattr(user, "last_name", None)
    display_name = " ".join(part for part in [first_name, last_name] if part).strip() or username or str(getattr(user, "id", "-"))
    phone = getattr(user, "phone", None) or "недоступен"
    premium = _yes_no_unknown(getattr(user, "premium", None))
    verified = _yes_no(getattr(user, "verified", False))
    scam = _yes_no(getattr(user, "scam", False))
    fake = _yes_no(getattr(user, "fake", False))
    restricted = _yes_no(getattr(user, "restricted", False))
    mutual = _yes_no_unknown(getattr(user, "mutual_contact", None))
    access_hash = _mask_access_hash(getattr(user, "access_hash", None))
    common = str(common_chats_count) if common_chats_count is not None else "недоступно"
    photos = str(profile_photo_count) if profile_photo_count is not None else "недоступно"
    return (
        "👤 <b>Информация о пользователе</b>\n\n"
        f"ID: <code>{getattr(user, 'id', '-')}</code>\n"
        f"Username: <code>{_q(('@' + username) if username else '-')}</code>\n"
        f"Имя: <code>{_q(first_name or '-')}</code>\n"
        f"Фамилия: <code>{_q(last_name or '-')}</code>\n"
        f"Display name: <code>{_q(display_name)}</code>\n"
        f"Bot: {_yes_no(getattr(user, 'bot', False))}\n"
        f"Premium: {premium}\n"
        f"Verified: {verified}\n"
        f"Scam/Fake: {scam}/{fake}\n"
        f"Restricted: {restricted}\n"
        f"Lang code: <code>{_q(getattr(user, 'lang_code', None) or '-')}</code>\n"
        f"Mutual contact: {mutual}\n"
        f"Телефон: <code>{_q(phone)}</code>\n"
        f"Access hash: <code>{_q(access_hash)}</code>\n"
        f"Common chats: <code>{common}</code>\n"
        f"Profile photos: <code>{photos}</code>\n"
        f"Статус: <code>{_status_text(getattr(user, 'status', None))}</code>\n"
        "Дата регистрации: недоступна через Telegram API\n\n"
        "<b>Чат:</b>\n"
        f"Chat ID: <code>{chat_id if chat_id is not None else '-'}</code>\n"
        f"Message ID: <code>{message_id if message_id is not None else '-'}</code>"
    )


def _yes_no(value: bool) -> str:
    return "да" if bool(value) else "нет"


def _q(value) -> str:
    return html.escape(str(value), quote=False)


def _yes_no_unknown(value) -> str:
    if value is None:
        return "неизвестно"
    return _yes_no(bool(value))


def _mask_access_hash(value) -> str:
    if value is None:
        return "-"
    text = str(value)
    if len(text) <= 6:
        return "***"
    return f"{text[:3]}...{text[-3:]}"


def _status_text(status) -> str:
    if isinstance(status, UserStatusOnline):
        return "online"
    if isinstance(status, UserStatusRecently):
        return "recently"
    if isinstance(status, UserStatusLastWeek):
        return "last week"
    if isinstance(status, UserStatusLastMonth):
        return "last month"
    if isinstance(status, UserStatusOffline):
        was_online = getattr(status, "was_online", None)
        if was_online:
            if getattr(was_online, "tzinfo", None) is not None:
                was_online = was_online.astimezone(UTC).replace(tzinfo=None)
            return f"offline, last seen {was_online:%Y-%m-%d %H:%M}"
        return "offline"
    return "hidden"

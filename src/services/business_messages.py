from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class BusinessUserSnapshot:
    user_id: int | None
    name: str | None
    username: str | None


@dataclass(slots=True)
class BusinessConnectionSnapshot:
    connection_id: str
    user: BusinessUserSnapshot
    user_chat_id: int | None
    date: datetime | None
    is_enabled: bool
    can_reply: bool | None
    rights: dict[str, Any] | None
    raw: dict[str, Any]


@dataclass(slots=True)
class BusinessMessageSnapshot:
    connection_id: str | None
    chat_id: int
    message_id: int
    sender: BusinessUserSnapshot
    chat_title: str | None
    text: str | None
    caption: str | None
    date: datetime
    edited_at: datetime | None
    reply_to: int | None
    media_type: str | None
    media_meta: dict[str, Any]
    raw: dict[str, Any]


@dataclass(slots=True)
class BusinessDeletedMessagesSnapshot:
    connection_id: str | None
    chat_id: int | None
    message_ids: list[int]
    raw: dict[str, Any]


def parse_business_connection(value: Any) -> BusinessConnectionSnapshot:
    raw = to_raw_dict(value)
    user = raw.get("user") or {}
    return BusinessConnectionSnapshot(
        connection_id=str(raw["id"]),
        user=_user_snapshot(user),
        user_chat_id=_int_or_none(raw.get("user_chat_id")),
        date=_to_datetime(raw.get("date")),
        is_enabled=bool(raw.get("is_enabled", True)),
        can_reply=raw.get("can_reply"),
        rights=raw.get("rights") if isinstance(raw.get("rights"), dict) else None,
        raw=raw,
    )


def parse_business_message(value: Any) -> BusinessMessageSnapshot:
    raw = to_raw_dict(value)
    chat = raw.get("chat") or {}
    sender = raw.get("from") or raw.get("from_user") or raw.get("sender_business_bot") or {}
    text = raw.get("text") or raw.get("caption")
    media_type, media_meta = extract_media_metadata(raw)
    return BusinessMessageSnapshot(
        connection_id=raw.get("business_connection_id"),
        chat_id=int(chat["id"]),
        message_id=int(raw["message_id"]),
        sender=_user_snapshot(sender),
        chat_title=chat.get("title") or chat.get("username") or _display_name(chat),
        text=text,
        caption=raw.get("caption"),
        date=_to_datetime(raw.get("date")) or datetime.now(UTC).replace(tzinfo=None),
        edited_at=_to_datetime(raw.get("edit_date")),
        reply_to=_reply_to_id(raw.get("reply_to_message")),
        media_type=media_type,
        media_meta=media_meta,
        raw=raw,
    )


def parse_deleted_business_messages(value: Any) -> BusinessDeletedMessagesSnapshot:
    raw = to_raw_dict(value)
    chat = raw.get("chat") or {}
    return BusinessDeletedMessagesSnapshot(
        connection_id=raw.get("business_connection_id"),
        chat_id=_int_or_none(chat.get("id")),
        message_ids=[int(item) for item in raw.get("message_ids", [])],
        raw=raw,
    )


def to_raw_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    raise TypeError(f"Unsupported business update payload: {type(value)!r}")


def extract_media_metadata(raw: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    for media_type in (
        "photo",
        "video",
        "animation",
        "document",
        "audio",
        "voice",
        "video_note",
        "sticker",
        "paid_media",
    ):
        if raw.get(media_type):
            return media_type, _media_payload(media_type, raw[media_type])
    return None, {}


def _media_payload(media_type: str, value: Any) -> dict[str, Any]:
    if media_type == "photo" and isinstance(value, list):
        photos = [item for item in value if isinstance(item, dict)]
        if not photos:
            return {"items": value}
        largest = max(photos, key=lambda item: item.get("file_size") or 0)
        return {"items": photos, "selected": largest}
    if isinstance(value, dict):
        return value
    return {"value": value}


def _user_snapshot(value: dict[str, Any]) -> BusinessUserSnapshot:
    return BusinessUserSnapshot(
        user_id=_int_or_none(value.get("id")),
        name=_display_name(value),
        username=value.get("username"),
    )


def _display_name(value: dict[str, Any]) -> str | None:
    first = value.get("first_name")
    last = value.get("last_name")
    full = " ".join(part for part in (first, last) if part)
    return full or value.get("title") or value.get("username")


def _reply_to_id(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    return _int_or_none(value.get("message_id"))


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC).replace(tzinfo=None)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            return parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed
    return None

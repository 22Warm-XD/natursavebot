from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.types import Message

from src.config import Settings
from src.db.models import MediaFile


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BusinessMedia:
    media_type: str | None
    file_id: str | None = None
    file_unique_id: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    duration: int | None = None
    width: int | None = None
    height: int | None = None
    local_path: str | None = None
    status: str | None = None
    error: str | None = None
    metadata: dict | None = None


def extract_business_media(message: Message, *, allow_voice_audio: bool = False) -> BusinessMedia:
    if message.photo:
        photo = message.photo[-1]
        return BusinessMedia("photo", photo.file_id, photo.file_unique_id, photo.file_size, width=photo.width, height=photo.height)
    if message.video:
        video = message.video
        return BusinessMedia("video", video.file_id, video.file_unique_id, video.file_size, video.mime_type, video.duration, video.width, video.height)
    if message.animation:
        animation = message.animation
        return BusinessMedia("animation", animation.file_id, animation.file_unique_id, animation.file_size, animation.mime_type, animation.duration, animation.width, animation.height)
    if allow_voice_audio and message.voice:
        voice = message.voice
        return BusinessMedia("voice", voice.file_id, voice.file_unique_id, voice.file_size, voice.mime_type, voice.duration)
    if allow_voice_audio and message.audio:
        audio = message.audio
        return BusinessMedia("audio", audio.file_id, audio.file_unique_id, audio.file_size, audio.mime_type, audio.duration)
    if message.document:
        document = message.document
        return BusinessMedia("document", document.file_id, document.file_unique_id, document.file_size, document.mime_type)
    if message.video_note:
        note = message.video_note
        return BusinessMedia("video_note", note.file_id, note.file_unique_id, note.file_size, duration=note.duration, width=note.length, height=note.length)
    if message.sticker:
        sticker = message.sticker
        return BusinessMedia("sticker", sticker.file_id, sticker.file_unique_id, sticker.file_size, width=sticker.width, height=sticker.height)
    paid_media = getattr(message, "paid_media", None)
    if paid_media:
        metadata = paid_media.model_dump(mode="json", by_alias=True, exclude_none=True) if hasattr(paid_media, "model_dump") else {"value": str(paid_media)}
        return BusinessMedia("paid_media", status="unavailable", metadata=metadata)
    return BusinessMedia(None)


def has_expiring_media_hint(message: Message) -> bool:
    raw = message.model_dump(mode="json", by_alias=True, exclude_none=True) if hasattr(message, "model_dump") else {}
    if getattr(message, "has_media_spoiler", False):
        return True
    text = " ".join(
        str(part or "").lower()
        for part in (
            getattr(message, "text", None),
            getattr(message, "caption", None),
        )
    )
    words = (
        "самоуничтож",
        "исчезающ",
        "истекающ",
        "посмотрите его на своём мобильном устройстве",
        "self-destruct",
        "self destruct",
        "view once",
        "expired",
        "ttl",
    )
    if any(word in text for word in words):
        return True
    return _contains_expiring_key(raw)


async def download_business_media(
    bot: Bot,
    message: Message,
    settings: Settings,
    *,
    allow_voice_audio: bool = False,
) -> BusinessMedia:
    media = extract_business_media(message, allow_voice_audio=allow_voice_audio)
    if not media.media_type or not media.file_id:
        return media
    media.metadata = {
        "file_id": media.file_id,
        "file_unique_id": media.file_unique_id,
        "file_size": media.file_size,
        "mime_type": media.mime_type,
        "duration": media.duration,
        "width": media.width,
        "height": media.height,
    }
    max_bytes = settings.effective_save_media_max_mb * 1024 * 1024
    if media.file_size and media.file_size > max_bytes:
        media.status = "too_large"
        return media
    attempts = 3 if has_expiring_media_hint(message) else 1
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            tg_file = await bot.get_file(media.file_id)
            ext = _extension(tg_file.file_path, media.media_type, media.mime_type)
            target_dir = Path(settings.media_dir) / str(message.chat.id)
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{message.message_id}_{media.media_type}{ext}"
            await bot.download_file(tg_file.file_path, destination=target)
            media.local_path = str(target)
            media.status = "downloaded"
            media.metadata["bot_file_path"] = tg_file.file_path
            media.metadata["local_path"] = str(target)
            return media
        except Exception as exc:
            last_error = exc
            logger.info("business media unavailable (attempt %s/%s): %s", attempt, attempts, exc)
            if attempt < attempts:
                await asyncio.sleep(0.45)
    media.status = "error"
    media.error = str(last_error) if last_error else "unknown"
    return media


def media_file_row(media: BusinessMedia, *, message_db_id: int | None, business_connection_id: str | None, chat_id: int, message_id: int) -> MediaFile | None:
    if not media.media_type:
        return None
    return MediaFile(
        message_db_id=message_db_id,
        source="business",
        business_connection_id=business_connection_id,
        chat_id=chat_id,
        message_id=message_id,
        media_type=media.media_type,
        file_id=media.file_id,
        file_unique_id=media.file_unique_id,
        file_size=media.file_size,
        mime_type=media.mime_type,
        duration=media.duration,
        width=media.width,
        height=media.height,
        local_path=media.local_path,
        status=media.status or "metadata",
        error=media.error,
        metadata_json=json.dumps(media.metadata or {}, ensure_ascii=False),
    )


def _extension(file_path: str | None, media_type: str, mime_type: str | None) -> str:
    if file_path and "." in file_path:
        return "." + file_path.rsplit(".", 1)[-1]
    by_type = {
        "photo": ".jpg",
        "video": ".mp4",
        "animation": ".mp4",
        "voice": ".ogg",
        "audio": ".mp3",
        "document": ".bin",
        "video_note": ".mp4",
        "sticker": ".webp",
    }
    if mime_type and "/" in mime_type:
        ext = mime_type.rsplit("/", 1)[-1].split(";")[0]
        if ext and len(ext) <= 5:
            return "." + ext
    return by_type.get(media_type, ".bin")


def _contains_expiring_key(value: Any) -> bool:
    keys = ("ttl", "self_destruct", "selfDestruct", "view_once", "viewOnce", "expire", "expired")
    if isinstance(value, dict):
        for key, item in value.items():
            if any(marker in str(key) for marker in keys):
                return True
            if _contains_expiring_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_expiring_key(item) for item in value)
    return False

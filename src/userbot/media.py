from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from telethon.tl.custom import Message

from src.config import Settings


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MediaResult:
    media_type: str | None
    path: str | None
    status: str | None
    metadata: dict


def media_type_of(message: Message, *, allow_voice_audio: bool = False) -> str | None:
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if allow_voice_audio and message.voice:
        return "voice"
    if allow_voice_audio and message.audio:
        return "audio"
    if message.video_note:
        return "video_note"
    if message.sticker:
        return "sticker"
    if message.document:
        return "document"
    if message.media:
        return "other"
    return None


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:120] or "media"


async def save_media_if_available(message: Message, settings: Settings, *, allow_voice_audio: bool = False) -> MediaResult:
    media_type = media_type_of(message, allow_voice_audio=allow_voice_audio)
    if not media_type:
        return MediaResult(None, None, None, {})

    size = getattr(getattr(message, "file", None), "size", None)
    ext = getattr(getattr(message, "file", None), "ext", None) or ".bin"
    name = getattr(getattr(message, "file", None), "name", None)
    metadata = {
        "size": size,
        "ext": ext,
        "name": name,
        "mime_type": getattr(getattr(message, "file", None), "mime_type", None),
    }
    max_bytes = settings.save_media_max_mb * 1024 * 1024
    if size and size > max_bytes:
        return MediaResult(media_type, None, "too_large", metadata)

    chat_part = str(message.chat_id or "unknown")
    filename = _safe_filename(f"{message.id}_{name or media_type}{ext if name is None else ''}")
    target_dir = Path(settings.media_dir) / chat_part
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename

    try:
        downloaded = await message.download_media(file=str(target))
        if not downloaded:
            return MediaResult(media_type, None, "unavailable", metadata)
        metadata["downloaded"] = True
        metadata["json"] = json.dumps(metadata, ensure_ascii=False)
        return MediaResult(media_type, str(downloaded), "saved", metadata)
    except Exception as exc:
        logger.info("media unavailable through standard API: %s", exc)
        return MediaResult(media_type, None, "protected", metadata)

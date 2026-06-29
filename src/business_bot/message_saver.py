from __future__ import annotations

import json
from datetime import UTC, datetime

from aiogram.types import BusinessMessagesDeleted, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.business_bot.media_downloader import BusinessMedia, media_file_row
from src.db.models import DeletedEvent, MediaFile, MessageEdit, SaveModeEvent
from src.db.repositories.chats import upsert_chat
from src.db.repositories.messages import find_messages_by_ids, get_message, mark_deleted, upsert_message


async def save_business_message(
    session: AsyncSession,
    message: Message,
    media: BusinessMedia | None = None,
    *,
    owner_id: int | None = None,
) -> object:
    sender = message.from_user
    sender_name = _user_name(sender)
    chat_title = (
        getattr(message.chat, "title", None)
        or getattr(message.chat, "full_name", None)
        or getattr(message.chat, "username", None)
        or str(message.chat.id)
    )
    await upsert_chat(
        session,
        chat_id=message.chat.id,
        title=chat_title,
        username=message.chat.username,
        chat_type=message.chat.type,
        is_bot=False,
    )
    row = await upsert_message(
        session,
        source="business",
        is_business=True,
        business_connection_id=message.business_connection_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
        sender_id=sender.id if sender else None,
        sender_name=sender_name,
        sender_username=sender.username if sender else None,
        chat_title=chat_title,
        direction="outgoing" if sender and owner_id and sender.id == owner_id else "incoming",
        text_value=message.text,
        caption=message.caption,
        date=_naive_utc(message.date) if message.date else datetime.now(UTC).replace(tzinfo=None),
        edited_at=_edit_date(message),
        reply_to=message.reply_to_message.message_id if message.reply_to_message else None,
        media_type=media.media_type if media else None,
        media_path=media.local_path if media else None,
        media_status=media.status if media else None,
        media_meta=(media.metadata if media else None),
        raw_json=message.model_dump_json(exclude_none=True),
    )
    if media and media.media_type:
        media_row = media_file_row(
            media,
            message_db_id=row.id,
            business_connection_id=message.business_connection_id,
            chat_id=message.chat.id,
            message_id=message.message_id,
        )
        if media_row:
            await _upsert_media_file(session, media_row)
    await session.flush()
    return row


async def save_business_edit(
    session: AsyncSession,
    message: Message,
    media: BusinessMedia | None = None,
    *,
    owner_id: int | None = None,
) -> tuple[object, MessageEdit | None, str | None]:
    old = await get_message(
        session,
        message.chat.id,
        message.message_id,
        source="business",
        business_connection_id=message.business_connection_id,
    )
    old_text = _message_body(old) if old else None
    row = await save_business_message(session, message, media, owner_id=owner_id)
    new_text = message.text or message.caption
    edit = MessageEdit(
        message_db_id=getattr(row, "id", None),
        source="business",
        business_connection_id=message.business_connection_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
        old_text=old_text,
        new_text=new_text,
        edited_at=_edit_date(message) or datetime.now(UTC).replace(tzinfo=None),
        raw_json=message.model_dump_json(exclude_none=True),
    )
    session.add(edit)
    session.add(
        SaveModeEvent(
            kind="edit" if old else "edit_untracked",
            business_connection_id=message.business_connection_id,
            chat_id=message.chat.id,
            message_id=message.message_id,
            sender_id=message.from_user.id if message.from_user else None,
            sender_name=_user_name(message.from_user),
            old_text=old_text,
            new_text=new_text,
            media_type=media.media_type if media else None,
            media_path=media.local_path if media else None,
            media_status=media.status if media else None,
            payload_json=message.model_dump_json(exclude_none=True),
        )
    )
    await session.flush()
    return row, edit, old_text


async def save_business_delete(
    session: AsyncSession,
    deleted: BusinessMessagesDeleted,
    *,
    owner_id: int | None = None,
) -> tuple[list[object], DeletedEvent | None]:
    found_messages = await find_messages_by_ids(
        session,
        list(deleted.message_ids),
        chat_id=deleted.chat.id,
        source="business",
        business_connection_id=deleted.business_connection_id,
    )
    messages = [message for message in found_messages if not _is_owner_message(message, owner_id)]
    now = datetime.now(UTC).replace(tzinfo=None)
    for message in found_messages:
        await mark_deleted(session, message, now)
        session.add(
            SaveModeEvent(
                kind="delete",
                business_connection_id=deleted.business_connection_id,
                chat_id=message.chat_id,
                message_id=message.message_id,
                sender_id=message.sender_id,
                sender_name=message.sender_name,
                text=_message_body(message),
                media_type=message.media_type,
                media_path=message.media_path,
                media_status=message.media_status,
                payload_json=deleted.model_dump_json(exclude_none=True),
                created_at=now,
            )
        )
    event = DeletedEvent(
        source="business",
        business_connection_id=deleted.business_connection_id,
        chat_id=deleted.chat.id,
        message_ids_json=json.dumps(list(deleted.message_ids)),
        found_count=len(found_messages),
        raw_json=deleted.model_dump_json(exclude_none=True),
        created_at=now,
    )
    session.add(event)
    await session.flush()
    return messages, event


def _message_body(message) -> str | None:
    if message is None:
        return None
    return getattr(message, "text", None) or getattr(message, "caption", None)


def _user_name(user) -> str | None:
    if user is None:
        return None
    return " ".join(part for part in [user.first_name, user.last_name] if part).strip() or user.username or str(user.id)


def _is_owner_message(message, owner_id: int | None) -> bool:
    if owner_id and getattr(message, "sender_id", None) == owner_id:
        return True
    return getattr(message, "direction", None) == "outgoing"


def _edit_date(message: Message) -> datetime | None:
    if not message.edit_date:
        return None
    if isinstance(message.edit_date, datetime):
        return _naive_utc(message.edit_date)
    return datetime.fromtimestamp(int(message.edit_date), UTC).replace(tzinfo=None)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


async def _upsert_media_file(session: AsyncSession, media_row: MediaFile) -> MediaFile:
    stmt = select(MediaFile).where(
        MediaFile.source == media_row.source,
        MediaFile.chat_id == media_row.chat_id,
        MediaFile.message_id == media_row.message_id,
        MediaFile.media_type == media_row.media_type,
    )
    if media_row.business_connection_id is None:
        stmt = stmt.where(MediaFile.business_connection_id.is_(None))
    else:
        stmt = stmt.where(MediaFile.business_connection_id == media_row.business_connection_id)
    if media_row.file_unique_id:
        stmt = stmt.where(MediaFile.file_unique_id == media_row.file_unique_id)
    elif media_row.file_id:
        stmt = stmt.where(MediaFile.file_id == media_row.file_id)

    existing = (await session.execute(stmt.order_by(MediaFile.id))).scalars().first()
    if existing is None:
        session.add(media_row)
        return media_row

    existing.message_db_id = media_row.message_db_id
    existing.file_id = media_row.file_id
    existing.file_unique_id = media_row.file_unique_id
    existing.file_size = media_row.file_size
    existing.mime_type = media_row.mime_type
    existing.duration = media_row.duration
    existing.width = media_row.width
    existing.height = media_row.height
    existing.local_path = media_row.local_path
    existing.status = media_row.status
    existing.error = media_row.error
    existing.metadata_json = media_row.metadata_json
    return existing

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Message, SaveModeEvent
from src.db.repositories.messages import find_messages_by_ids, get_message, mark_deleted, save_edit
from src.db.repositories.save_mode import create_save_event


@dataclass(slots=True)
class SaveModeNotification:
    kind: str
    event: SaveModeEvent
    message: Message | None = None


async def record_delete(
    session: AsyncSession,
    *,
    message_ids: list[int],
    chat_id: int | None,
    deleted_at: datetime | None = None,
    allowed_chat_ids: set[int] | None = None,
) -> list[SaveModeNotification]:
    deleted_at = deleted_at or datetime.now(UTC).replace(tzinfo=None)
    messages = await find_messages_by_ids(session, message_ids, chat_id=chat_id)
    notes: list[SaveModeNotification] = []
    for message in messages:
        if allowed_chat_ids is not None and message.chat_id not in allowed_chat_ids:
            continue
        await mark_deleted(session, message, deleted_at)
        event = await create_save_event(
            session,
            kind="delete",
            chat_id=message.chat_id,
            message_id=message.message_id,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            text=message.text,
            media_type=message.media_type,
            media_path=message.media_path,
            media_status=message.media_status,
            created_at=deleted_at,
        )
        notes.append(SaveModeNotification(kind="delete", event=event, message=message))
    return notes


async def record_edit(
    session: AsyncSession,
    *,
    chat_id: int,
    message_id: int,
    new_text: str | None,
    edited_at: datetime | None = None,
) -> SaveModeNotification | None:
    edited_at = edited_at or datetime.now(UTC).replace(tzinfo=None)
    message = await get_message(session, chat_id, message_id)
    if message is None:
        event = await create_save_event(
            session,
            kind="edit_untracked",
            chat_id=chat_id,
            message_id=message_id,
            new_text=new_text,
            created_at=edited_at,
        )
        return SaveModeNotification(kind="edit_untracked", event=event, message=None)
    if (message.text or "") == (new_text or ""):
        return None
    old_text = message.text
    await save_edit(session, message, new_text, edited_at)
    event = await create_save_event(
        session,
        kind="edit",
        chat_id=message.chat_id,
        message_id=message.message_id,
        sender_id=message.sender_id,
        sender_name=message.sender_name,
        old_text=old_text,
        new_text=new_text,
        media_type=message.media_type,
        media_path=message.media_path,
        media_status=message.media_status,
        created_at=edited_at,
    )
    return SaveModeNotification(kind="edit", event=event, message=message)


async def record_media_unavailable(
    session: AsyncSession,
    *,
    chat_id: int,
    message_id: int,
    sender_id: int | None,
    sender_name: str | None,
    media_type: str | None,
    status: str,
) -> SaveModeEvent:
    return await create_save_event(
        session,
        kind="media_unavailable",
        chat_id=chat_id,
        message_id=message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        media_type=media_type,
        media_status=status,
    )

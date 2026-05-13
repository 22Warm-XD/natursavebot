from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DeletedEvent, Message, MessageEdit, SaveModeEvent
from src.db.repositories.business import upsert_business_connection
from src.db.repositories.messages import get_message, mark_deleted, save_edit, upsert_message
from src.db.repositories.save_mode import create_save_event
from src.services.business_messages import (
    BusinessConnectionSnapshot,
    BusinessDeletedMessagesSnapshot,
    BusinessMessageSnapshot,
    parse_business_connection,
    parse_business_message,
    parse_deleted_business_messages,
    to_raw_dict,
)


@dataclass(slots=True)
class BusinessSaveModeNotification:
    kind: str
    event: SaveModeEvent
    message: Message | None = None


async def record_business_connection(
    session: AsyncSession,
    connection: Any,
) -> BusinessSaveModeNotification:
    snapshot = connection if isinstance(connection, BusinessConnectionSnapshot) else parse_business_connection(connection)
    await upsert_business_connection(
        session,
        connection_id=snapshot.connection_id,
        user_id=snapshot.user.user_id,
        user_name=snapshot.user.name,
        user_username=snapshot.user.username,
        user_chat_id=snapshot.user_chat_id,
        date=snapshot.date,
        is_enabled=snapshot.is_enabled,
        can_reply=snapshot.can_reply,
        rights=snapshot.rights,
        raw_json=_json(snapshot.raw),
    )
    event = await create_save_event(
        session,
        kind="business_connection",
        chat_id=snapshot.user_chat_id,
        business_connection_id=snapshot.connection_id,
        sender_id=snapshot.user.user_id,
        sender_name=snapshot.user.name,
        payload_json=_json(snapshot.raw),
        created_at=snapshot.date or _now(),
    )
    return BusinessSaveModeNotification(kind="business_connection", event=event)


async def record_business_message(
    session: AsyncSession,
    message: Any,
) -> BusinessSaveModeNotification:
    snapshot = message if isinstance(message, BusinessMessageSnapshot) else parse_business_message(message)
    row = await upsert_message(
        session,
        source="business",
        chat_id=snapshot.chat_id,
        message_id=snapshot.message_id,
        sender_id=snapshot.sender.user_id,
        sender_name=snapshot.sender.name,
        sender_username=snapshot.sender.username,
        chat_title=snapshot.chat_title,
        direction="incoming",
        text_value=snapshot.text,
        caption=snapshot.caption,
        date=snapshot.date,
        edited_at=snapshot.edited_at,
        business_connection_id=snapshot.connection_id,
        is_business=True,
        reply_to=snapshot.reply_to,
        media_type=snapshot.media_type,
        media_status="metadata_only" if snapshot.media_type else None,
        media_meta=snapshot.media_meta or None,
        raw_json=_json(snapshot.raw),
    )
    event = await create_save_event(
        session,
        kind="business_message",
        chat_id=snapshot.chat_id,
        message_id=snapshot.message_id,
        business_connection_id=snapshot.connection_id,
        sender_id=snapshot.sender.user_id,
        sender_name=snapshot.sender.name,
        text=snapshot.text,
        media_type=snapshot.media_type,
        media_status="metadata_only" if snapshot.media_type else None,
        payload_json=_json(snapshot.raw),
        created_at=snapshot.date,
    )
    return BusinessSaveModeNotification(kind="business_message", event=event, message=row)


async def record_edited_business_message(
    session: AsyncSession,
    message: Any,
) -> BusinessSaveModeNotification | None:
    snapshot = message if isinstance(message, BusinessMessageSnapshot) else parse_business_message(message)
    edited_at = snapshot.edited_at or snapshot.date
    existing = await get_message(session, snapshot.chat_id, snapshot.message_id)
    if existing is None:
        row = await upsert_message(
            session,
            source="business",
            chat_id=snapshot.chat_id,
            message_id=snapshot.message_id,
            sender_id=snapshot.sender.user_id,
            sender_name=snapshot.sender.name,
            sender_username=snapshot.sender.username,
            chat_title=snapshot.chat_title,
            direction="incoming",
            text_value=snapshot.text,
            caption=snapshot.caption,
            date=snapshot.date,
            edited_at=edited_at,
            business_connection_id=snapshot.connection_id,
            is_business=True,
            reply_to=snapshot.reply_to,
            media_type=snapshot.media_type,
            media_status="metadata_only" if snapshot.media_type else None,
            media_meta=snapshot.media_meta or None,
            raw_json=_json(snapshot.raw),
        )
        session.add(
            MessageEdit(
                message_db_id=row.id,
                source="business",
                business_connection_id=snapshot.connection_id,
                chat_id=snapshot.chat_id,
                message_id=snapshot.message_id,
                old_text=None,
                new_text=snapshot.text,
                edited_at=edited_at,
                raw_json=_json(snapshot.raw),
            )
        )
        event = await create_save_event(
            session,
            kind="business_edit_untracked",
            chat_id=snapshot.chat_id,
            message_id=snapshot.message_id,
            business_connection_id=snapshot.connection_id,
            sender_id=snapshot.sender.user_id,
            sender_name=snapshot.sender.name,
            new_text=snapshot.text,
            media_type=snapshot.media_type,
            media_status="metadata_only" if snapshot.media_type else None,
            payload_json=_json(snapshot.raw),
            created_at=edited_at,
        )
        return BusinessSaveModeNotification(kind="business_edit_untracked", event=event, message=row)

    old_text = existing.text
    text_changed = (old_text or "") != (snapshot.text or "")
    if text_changed:
        await save_edit(session, existing, snapshot.text, edited_at)
        session.add(
            MessageEdit(
                message_db_id=existing.id,
                source="business",
                business_connection_id=snapshot.connection_id,
                chat_id=snapshot.chat_id,
                message_id=snapshot.message_id,
                old_text=old_text,
                new_text=snapshot.text,
                edited_at=edited_at,
                raw_json=_json(snapshot.raw),
            )
        )
    row = await upsert_message(
        session,
        source="business",
        chat_id=snapshot.chat_id,
        message_id=snapshot.message_id,
        sender_id=snapshot.sender.user_id,
        sender_name=snapshot.sender.name,
        sender_username=snapshot.sender.username,
        chat_title=snapshot.chat_title,
        direction=existing.direction,
        text_value=snapshot.text,
        caption=snapshot.caption,
        date=existing.date,
        edited_at=edited_at,
        business_connection_id=snapshot.connection_id,
        is_business=True,
        reply_to=snapshot.reply_to,
        media_type=snapshot.media_type,
        media_status="metadata_only" if snapshot.media_type else existing.media_status,
        media_meta=snapshot.media_meta or None,
        raw_json=_json(snapshot.raw),
    )
    if not text_changed and not snapshot.media_type:
        return None
    event = await create_save_event(
        session,
        kind="business_edit",
        chat_id=snapshot.chat_id,
        message_id=snapshot.message_id,
        business_connection_id=snapshot.connection_id,
        sender_id=snapshot.sender.user_id,
        sender_name=snapshot.sender.name,
        old_text=old_text,
        new_text=snapshot.text,
        media_type=snapshot.media_type or existing.media_type,
        media_path=existing.media_path,
        media_status=row.media_status,
        payload_json=_json(snapshot.raw),
        created_at=edited_at,
    )
    return BusinessSaveModeNotification(kind="business_edit", event=event, message=row)


async def record_deleted_business_messages(
    session: AsyncSession,
    deleted: Any,
    *,
    deleted_at: datetime | None = None,
) -> list[BusinessSaveModeNotification]:
    snapshot = deleted if isinstance(deleted, BusinessDeletedMessagesSnapshot) else parse_deleted_business_messages(deleted)
    deleted_at = deleted_at or _now()
    notes: list[BusinessSaveModeNotification] = []
    found_count = 0
    for message_id in snapshot.message_ids:
        message = await get_message(session, snapshot.chat_id, message_id) if snapshot.chat_id is not None else None
        if message is not None:
            await mark_deleted(session, message, deleted_at)
            found_count += 1
        event = await create_save_event(
            session,
            kind="business_delete",
            chat_id=snapshot.chat_id,
            message_id=message_id,
            business_connection_id=snapshot.connection_id,
            sender_id=message.sender_id if message else None,
            sender_name=message.sender_name if message else None,
            text=message.text if message else None,
            media_type=message.media_type if message else None,
            media_path=message.media_path if message else None,
            media_status=message.media_status if message else None,
            payload_json=_json(snapshot.raw),
            created_at=deleted_at,
        )
        notes.append(BusinessSaveModeNotification(kind="business_delete", event=event, message=message))
    session.add(
        DeletedEvent(
            source="business",
            business_connection_id=snapshot.connection_id,
            chat_id=snapshot.chat_id,
            message_ids_json=json.dumps(snapshot.message_ids),
            found_count=found_count,
            raw_json=_json(snapshot.raw),
            created_at=deleted_at,
        )
    )
    return notes


async def record_business_update(session: AsyncSession, update: Any) -> list[BusinessSaveModeNotification]:
    raw = to_raw_dict(update)
    notes: list[BusinessSaveModeNotification] = []
    if raw.get("business_connection"):
        notes.append(await record_business_connection(session, raw["business_connection"]))
    if raw.get("business_message"):
        notes.append(await record_business_message(session, raw["business_message"]))
    if raw.get("edited_business_message"):
        note = await record_edited_business_message(session, raw["edited_business_message"])
        if note is not None:
            notes.append(note)
    if raw.get("deleted_business_messages"):
        notes.extend(await record_deleted_business_messages(session, raw["deleted_business_messages"]))
    return notes


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

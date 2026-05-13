from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import desc, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DraftMessage, EditHistory, Message
from src.utils.text import make_fts_query


_message_schema_checked: set[str] = set()


async def upsert_message(
    session: AsyncSession,
    *,
    chat_id: int,
    message_id: int,
    sender_id: int | None,
    sender_name: str | None,
    sender_username: str | None,
    chat_title: str | None,
    direction: str,
    text_value: str | None,
    date: datetime,
    source: str = "telethon",
    business_connection_id: str | None = None,
    is_business: bool = False,
    caption: str | None = None,
    edited_at: datetime | None = None,
    reply_to: int | None = None,
    media_type: str | None = None,
    media_path: str | None = None,
    media_status: str | None = None,
    media_meta: dict | None = None,
    raw_json: str | None = None,
) -> Message:
    await _ensure_message_business_columns(session)
    row = (
        await session.execute(select(Message).where(Message.chat_id == chat_id, Message.message_id == message_id))
    ).scalar_one_or_none()
    payload = json.dumps(media_meta, ensure_ascii=False) if media_meta else None
    if row is None:
        row = Message(
            source=source,
            chat_id=chat_id,
            message_id=message_id,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_username=sender_username,
            chat_title=chat_title,
            direction=direction,
            business_connection_id=business_connection_id,
            is_business=is_business,
            text=text_value,
            caption=caption,
            date=date,
            edited_at=edited_at,
            reply_to=reply_to,
            media_type=media_type,
            media_path=media_path,
            media_status=media_status,
            media_meta_json=payload,
            raw_json=raw_json,
        )
        session.add(row)
    else:
        row.source = source or row.source
        row.sender_id = sender_id
        row.sender_name = sender_name
        row.sender_username = sender_username
        row.chat_title = chat_title
        row.direction = direction
        row.business_connection_id = business_connection_id or row.business_connection_id
        row.is_business = is_business or row.is_business
        row.text = text_value
        row.caption = caption
        row.date = date
        row.edited_at = edited_at or row.edited_at
        row.reply_to = reply_to
        row.media_type = media_type or row.media_type
        row.media_path = media_path or row.media_path
        row.media_status = media_status or row.media_status
        row.media_meta_json = payload or row.media_meta_json
        row.raw_json = raw_json or row.raw_json
    await session.flush()
    return row


async def get_message(session: AsyncSession, chat_id: int, message_id: int) -> Message | None:
    await _ensure_message_business_columns(session)
    return (
        await session.execute(select(Message).where(Message.chat_id == chat_id, Message.message_id == message_id))
    ).scalar_one_or_none()


async def find_messages_by_ids(session: AsyncSession, message_ids: list[int], chat_id: int | None = None) -> list[Message]:
    await _ensure_message_business_columns(session)
    stmt = select(Message).where(Message.message_id.in_(message_ids))
    if chat_id is not None:
        stmt = stmt.where(Message.chat_id == chat_id)
    return list((await session.execute(stmt.order_by(desc(Message.date)))).scalars())


async def save_edit(session: AsyncSession, message: Message, new_text: str | None, edited_at: datetime) -> EditHistory:
    history = EditHistory(
        message_db_id=message.id,
        chat_id=message.chat_id,
        message_id=message.message_id,
        old_text=message.text,
        new_text=new_text,
        edited_at=edited_at,
    )
    session.add(history)
    message.text = new_text
    await session.flush()
    return history


async def mark_deleted(session: AsyncSession, message: Message, deleted_at: datetime) -> Message:
    message.deleted = True
    message.deleted_at = deleted_at
    await session.flush()
    return message


async def recent_messages(session: AsyncSession, chat_id: int, *, limit: int = 80) -> list[Message]:
    stmt = select(Message).where(Message.chat_id == chat_id).order_by(desc(Message.date)).limit(limit)
    rows = list((await session.execute(stmt)).scalars())
    return list(reversed(rows))


async def search_messages(session: AsyncSession, query: str, *, limit: int = 20) -> list[Message]:
    fts_query = make_fts_query(query)
    if fts_query:
        try:
            result = await session.execute(
                text(
                    """
                    SELECT m.id FROM messages_fts f
                    JOIN messages m ON m.id = f.rowid
                    WHERE messages_fts MATCH :query
                    ORDER BY bm25(messages_fts)
                    LIMIT :limit
                    """
                ),
                {"query": fts_query, "limit": limit},
            )
            ids = [int(row[0]) for row in result.fetchall()]
            if ids:
                order = {message_id: index for index, message_id in enumerate(ids)}
                rows = list((await session.execute(select(Message).where(Message.id.in_(ids)))).scalars())
                return sorted(rows, key=lambda item: order[item.id])
        except Exception:
            pass
    like = f"%{query}%"
    stmt = (
        select(Message)
        .where(or_(Message.text.ilike(like), Message.sender_name.ilike(like), Message.chat_title.ilike(like)))
        .order_by(desc(Message.date))
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


async def latest_deleted(session: AsyncSession, *, limit: int = 20) -> list[Message]:
    return list((await session.execute(select(Message).where(Message.deleted.is_(True)).order_by(desc(Message.deleted_at)).limit(limit))).scalars())


async def latest_media(session: AsyncSession, *, limit: int = 20) -> list[Message]:
    return list((await session.execute(select(Message).where(Message.media_path.is_not(None)).order_by(desc(Message.date)).limit(limit))).scalars())


async def create_draft(
    session: AsyncSession,
    *,
    chat_id: int,
    recipient_label: str,
    text_value: str,
    business_connection_id: str | None = None,
) -> DraftMessage:
    draft = DraftMessage(
        id=uuid4().hex,
        chat_id=chat_id,
        recipient_label=recipient_label,
        text=text_value,
        business_connection_id=business_connection_id,
    )
    session.add(draft)
    await session.flush()
    return draft


async def get_draft(session: AsyncSession, draft_id: str) -> DraftMessage | None:
    return await session.get(DraftMessage, draft_id)


async def _ensure_message_business_columns(session: AsyncSession) -> None:
    bind = session.get_bind()
    schema_key = str(bind.url)
    if schema_key in _message_schema_checked:
        return
    if bind.dialect.name != "sqlite":
        _message_schema_checked.add(schema_key)
        return
    columns = {
        row[1]
        for row in (
            await session.execute(text("PRAGMA table_info(messages)"))
        ).all()
    }
    if "business_connection_id" not in columns:
        await session.execute(text("ALTER TABLE messages ADD COLUMN business_connection_id VARCHAR(255)"))
    if "is_business" not in columns:
        await session.execute(text("ALTER TABLE messages ADD COLUMN is_business BOOLEAN NOT NULL DEFAULT 0"))
    _message_schema_checked.add(schema_key)

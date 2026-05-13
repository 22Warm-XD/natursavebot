from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Chat


async def upsert_chat(
    session: AsyncSession,
    *,
    chat_id: int,
    title: str | None,
    username: str | None = None,
    chat_type: str = "unknown",
    is_archived: bool = False,
    is_bot: bool = False,
) -> Chat:
    row = (await session.execute(select(Chat).where(Chat.chat_id == chat_id))).scalar_one_or_none()
    if row is None:
        row = Chat(
            chat_id=chat_id,
            title=title,
            username=username,
            chat_type=chat_type,
            is_archived=is_archived,
            is_bot=is_bot,
            last_seen_at=datetime.now(UTC).replace(tzinfo=None),
        )
        session.add(row)
    else:
        row.title = title or row.title
        row.username = username or row.username
        row.chat_type = chat_type or row.chat_type
        row.is_archived = is_archived
        row.is_bot = is_bot
        row.last_seen_at = datetime.now(UTC).replace(tzinfo=None)
    await session.flush()
    return row


async def find_chats(session: AsyncSession, query: str, *, limit: int = 10) -> list[Chat]:
    like = f"%{query.strip().lower()}%"
    stmt = (
        select(Chat)
        .where(or_(Chat.title.ilike(like), Chat.username.ilike(like)))
        .order_by(Chat.last_seen_at.desc().nullslast())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


async def get_chat_by_id(session: AsyncSession, chat_id: int) -> Chat | None:
    return (await session.execute(select(Chat).where(Chat.chat_id == chat_id))).scalar_one_or_none()


async def set_chat_muted(session: AsyncSession, chat_id: int, muted: bool) -> None:
    chat = await get_chat_by_id(session, chat_id)
    if chat is not None:
        chat.muted_project = muted
        await session.flush()


async def set_chat_filter(session: AsyncSession, chat_id: int, *, whitelisted: bool | None = None, blacklisted: bool | None = None) -> None:
    chat = await get_chat_by_id(session, chat_id)
    if chat is None:
        return
    if whitelisted is not None:
        chat.whitelisted = whitelisted
    if blacklisted is not None:
        chat.blacklisted = blacklisted
    await session.flush()

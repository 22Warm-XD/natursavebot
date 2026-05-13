from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ChatSetting, utcnow


async def get_chat_setting(session: AsyncSession, chat_id: int) -> ChatSetting | None:
    return await session.get(ChatSetting, chat_id)


async def upsert_chat_setting(
    session: AsyncSession,
    *,
    chat_id: int,
    chat_title: str | None = None,
    username: str | None = None,
    hard_mute_delete_for_everyone: bool = True,
) -> ChatSetting:
    row = await session.get(ChatSetting, chat_id)
    if row is None:
        row = ChatSetting(
            chat_id=chat_id,
            chat_title=chat_title,
            username=username,
            hard_mute_delete_for_everyone=hard_mute_delete_for_everyone,
        )
        session.add(row)
    else:
        row.chat_title = chat_title or row.chat_title
        row.username = username or row.username
        row.hard_mute_delete_for_everyone = hard_mute_delete_for_everyone
    await session.flush()
    return row


async def set_hard_mute(
    session: AsyncSession,
    *,
    chat_id: int,
    enabled: bool,
    chat_title: str | None = None,
    username: str | None = None,
    delete_for_everyone: bool = True,
    until: datetime | None = None,
) -> ChatSetting:
    row = await upsert_chat_setting(
        session,
        chat_id=chat_id,
        chat_title=chat_title,
        username=username,
        hard_mute_delete_for_everyone=delete_for_everyone,
    )
    row.hard_muted = enabled
    row.hard_muted_at = utcnow() if enabled else row.hard_muted_at
    row.hard_muted_until = until if enabled else None
    row.updated_at = utcnow()
    await session.flush()
    return row


def hard_mute_active(setting: ChatSetting | None, *, now: datetime | None = None) -> bool:
    if setting is None or not setting.hard_muted:
        return False
    if setting.hard_muted_until is None:
        return True
    return (now or utcnow()) < setting.hard_muted_until

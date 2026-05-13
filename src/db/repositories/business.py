from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import BusinessConnection


_business_schema_checked: set[str] = set()


async def upsert_business_connection(
    session: AsyncSession,
    *,
    connection_id: str,
    user_id: int | None,
    user_name: str | None,
    user_username: str | None,
    user_chat_id: int | None,
    date: datetime | None,
    is_enabled: bool,
    can_reply: bool | None,
    rights: dict | None = None,
    raw_json: str | None = None,
) -> BusinessConnection:
    await _ensure_business_connection_table(session)
    row = (
        await session.execute(
            select(BusinessConnection).where(BusinessConnection.connection_id == connection_id)
        )
    ).scalar_one_or_none()
    rights_json = json.dumps(rights, ensure_ascii=False) if rights else None
    if row is None:
        row = BusinessConnection(connection_id=connection_id)
        session.add(row)
    row.user_id = user_id
    row.user_name = user_name
    row.user_username = user_username
    row.user_chat_id = user_chat_id
    row.date = date
    row.is_enabled = is_enabled
    row.can_reply = can_reply
    row.rights_json = rights_json
    row.raw_json = raw_json
    await session.flush()
    return row


async def get_business_connection(session: AsyncSession, connection_id: str) -> BusinessConnection | None:
    await _ensure_business_connection_table(session)
    return (
        await session.execute(
            select(BusinessConnection).where(BusinessConnection.connection_id == connection_id)
        )
    ).scalar_one_or_none()


async def _ensure_business_connection_table(session: AsyncSession) -> None:
    bind = session.get_bind()
    schema_key = str(bind.url)
    if schema_key in _business_schema_checked:
        return
    if bind.dialect.name == "sqlite":
        await session.run_sync(
            lambda sync_session: BusinessConnection.__table__.create(sync_session.get_bind(), checkfirst=True)
        )
    _business_schema_checked.add(schema_key)

from __future__ import annotations

import json

from aiogram.types import BusinessConnection as TgBusinessConnection
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import BusinessConnection


async def save_business_connection(session: AsyncSession, connection: TgBusinessConnection) -> BusinessConnection:
    row = (
        await session.execute(
            select(BusinessConnection).where(BusinessConnection.connection_id == connection.id)
        )
    ).scalar_one_or_none()
    user = connection.user
    rights_json = connection.rights.model_dump_json(exclude_none=True) if connection.rights else None
    raw_json = connection.model_dump_json(exclude_none=True)
    name = " ".join(part for part in [user.first_name, user.last_name] if part).strip() or user.username
    date_value = connection.date.replace(tzinfo=None) if connection.date else None
    if row is None:
        row = BusinessConnection(
            connection_id=connection.id,
            user_id=user.id,
            user_name=name,
            user_username=user.username,
            user_chat_id=connection.user_chat_id,
            date=date_value,
            is_enabled=connection.is_enabled,
            can_reply=connection.can_reply,
            rights_json=rights_json,
            raw_json=raw_json,
        )
        session.add(row)
    else:
        row.user_id = user.id
        row.user_name = name
        row.user_username = user.username
        row.user_chat_id = connection.user_chat_id
        row.date = date_value or row.date
        row.is_enabled = connection.is_enabled
        row.can_reply = connection.can_reply
        row.rights_json = rights_json
        row.raw_json = raw_json
    await session.flush()
    return row


async def latest_business_connection(session: AsyncSession, *, enabled_only: bool = True) -> BusinessConnection | None:
    stmt = select(BusinessConnection)
    if enabled_only:
        stmt = stmt.where(BusinessConnection.is_enabled.is_(True))
    return (await session.execute(stmt.order_by(desc(BusinessConnection.updated_at)).limit(1))).scalar_one_or_none()


def rights_summary(connection: BusinessConnection | None) -> str:
    if connection is None:
        return "Business-аккаунт пока не подключён."
    rights = {}
    if connection.rights_json:
        try:
            rights = json.loads(connection.rights_json)
        except json.JSONDecodeError:
            rights = {}
    enabled_rights = [key for key, value in rights.items() if value is True]
    rights_line = ", ".join(enabled_rights) if enabled_rights else "Telegram API не передал список прав"
    return (
        f"Статус: {'enabled' if connection.is_enabled else 'disabled'}\n"
        f"Business connection: {connection.connection_id}\n"
        f"Owner user id: {connection.user_id}\n"
        f"Can reply: {connection.can_reply}\n"
        f"Rights: {rights_line}"
    )

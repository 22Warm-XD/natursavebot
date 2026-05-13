from __future__ import annotations

from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import SaveModeEvent


_event_schema_checked: set[str] = set()


async def create_save_event(session: AsyncSession, **kwargs) -> SaveModeEvent:
    await _ensure_event_business_columns(session)
    event = SaveModeEvent(**kwargs)
    session.add(event)
    await session.flush()
    return event


async def latest_events(session: AsyncSession, kind: str | None = None, *, limit: int = 20) -> list[SaveModeEvent]:
    await _ensure_event_business_columns(session)
    stmt = select(SaveModeEvent)
    if kind:
        stmt = stmt.where(SaveModeEvent.kind == kind)
    stmt = stmt.order_by(desc(SaveModeEvent.created_at)).limit(limit)
    return list((await session.execute(stmt)).scalars())


async def stats(session: AsyncSession) -> dict[str, int]:
    await _ensure_event_business_columns(session)
    rows = await session.execute(select(SaveModeEvent.kind, func.count()).group_by(SaveModeEvent.kind))
    return {kind: count for kind, count in rows.all()}


async def _ensure_event_business_columns(session: AsyncSession) -> None:
    bind = session.get_bind()
    schema_key = str(bind.url)
    if schema_key in _event_schema_checked:
        return
    if bind.dialect.name != "sqlite":
        _event_schema_checked.add(schema_key)
        return
    columns = {
        row[1]
        for row in (
            await session.execute(text("PRAGMA table_info(save_mode_events)"))
        ).all()
    }
    if "business_connection_id" not in columns:
        await session.execute(text("ALTER TABLE save_mode_events ADD COLUMN business_connection_id VARCHAR(255)"))
    if "payload_json" not in columns:
        await session.execute(text("ALTER TABLE save_mode_events ADD COLUMN payload_json TEXT"))
    _event_schema_checked.add(schema_key)

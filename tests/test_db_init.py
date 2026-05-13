from __future__ import annotations

from sqlalchemy import text

from src.db.session import get_session, init_db


async def test_init_db_creates_messages_table_directly(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'direct.db'}")

    async with get_session() as session:
        result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"))

    assert result.scalar_one_or_none() == "messages"

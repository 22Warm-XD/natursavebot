from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings
from src.db.base import Base


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def configure_engine(database_url: str | None = None) -> AsyncEngine:
    global _engine, _sessionmaker
    url = database_url or get_settings().database_url
    if url.startswith("sqlite+aiosqlite:///"):
        raw_path = url.removeprefix("sqlite+aiosqlite:///")
        if raw_path != ":memory:":
            Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
    _engine = create_async_engine(url, echo=False, future=True)
    if url.startswith("sqlite+aiosqlite:///"):
        sync_engine = _engine.sync_engine

        @event.listens_for(sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        return configure_engine()
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        configure_engine()
    assert _sessionmaker is not None
    return _sessionmaker


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    maker = get_sessionmaker()
    async with maker() as session:
        yield session


async def init_db(database_url: str | None = None) -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
    import src.db.models  # noqa: F401  Ensures all SQLAlchemy models are registered.

    engine = configure_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name != "sqlite":
            return
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await _ensure_sqlite_columns(conn)
        await conn.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
                USING fts5(text, sender_name, chat_title, content='messages', content_rowid='id')
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                    INSERT INTO messages_fts(rowid, text, sender_name, chat_title)
                    VALUES (new.id, coalesce(new.text, ''), coalesce(new.sender_name, ''), coalesce(new.chat_title, ''));
                END;
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                    INSERT INTO messages_fts(messages_fts, rowid, text, sender_name, chat_title)
                    VALUES('delete', old.id, coalesce(old.text, ''), coalesce(old.sender_name, ''), coalesce(old.chat_title, ''));
                END;
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE OF text, sender_name, chat_title ON messages BEGIN
                    INSERT INTO messages_fts(messages_fts, rowid, text, sender_name, chat_title)
                    VALUES('delete', old.id, coalesce(old.text, ''), coalesce(old.sender_name, ''), coalesce(old.chat_title, ''));
                    INSERT INTO messages_fts(rowid, text, sender_name, chat_title)
                    VALUES (new.id, coalesce(new.text, ''), coalesce(new.sender_name, ''), coalesce(new.chat_title, ''));
                END;
                """
            )
        )


async def _ensure_sqlite_columns(conn) -> None:
    columns_by_table: dict[str, dict[str, str]] = {
        "messages": {
            "source": "TEXT NOT NULL DEFAULT 'telethon'",
            "business_connection_id": "TEXT",
            "is_business": "INTEGER NOT NULL DEFAULT 0",
            "caption": "TEXT",
            "edited_at": "DATETIME",
            "raw_json": "TEXT",
        },
        "business_connections": {
            "allowed_chats_mode": "TEXT",
            "raw_json": "TEXT",
        },
        "save_mode_events": {
            "business_connection_id": "TEXT",
            "payload_json": "TEXT",
        },
        "draft_messages": {
            "business_connection_id": "TEXT",
        },
        "chat_settings": {
            "chat_title": "VARCHAR(512)",
            "username": "VARCHAR(255)",
            "hard_muted": "BOOLEAN NOT NULL DEFAULT 0",
            "hard_muted_at": "DATETIME",
            "hard_muted_until": "DATETIME",
            "hard_mute_delete_for_everyone": "BOOLEAN NOT NULL DEFAULT 1",
            "save_mode_enabled": "BOOLEAN",
            "notify_enabled": "BOOLEAN",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        },
        "hard_mute_events": {
            "sender_username": "VARCHAR(255)",
            "media_file_id": "TEXT",
            "media_local_path": "TEXT",
            "delete_for_everyone_success": "BOOLEAN NOT NULL DEFAULT 0",
            "delete_local_success": "BOOLEAN NOT NULL DEFAULT 0",
            "delete_error": "TEXT",
            "raw_json": "TEXT",
        },
    }
    for table, columns in columns_by_table.items():
        existing = await conn.execute(text(f"PRAGMA table_info({table})"))
        existing_names = {row[1] for row in existing.fetchall()}
        for name, definition in columns.items():
            if name not in existing_names:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))

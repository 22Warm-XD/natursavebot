from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Todo


async def create_todo(
    session: AsyncSession,
    *,
    title: str,
    actor: str | None = None,
    deadline_at: datetime | None = None,
    chat_id: int | None = None,
    message_id: int | None = None,
    source_text: str | None = None,
) -> Todo:
    todo = Todo(
        title=title,
        actor=actor,
        deadline_at=deadline_at,
        chat_id=chat_id,
        message_id=message_id,
        source_text=source_text,
    )
    session.add(todo)
    await session.flush()
    return todo


async def list_todos(session: AsyncSession, *, status: str = "open", limit: int = 30) -> list[Todo]:
    stmt = select(Todo).where(Todo.status == status).order_by(Todo.deadline_at.asc().nullslast(), desc(Todo.created_at)).limit(limit)
    return list((await session.execute(stmt)).scalars())


async def set_todo_status(session: AsyncSession, todo_id: int, status: str) -> Todo | None:
    todo = await session.get(Todo, todo_id)
    if todo:
        todo.status = status
        await session.flush()
    return todo

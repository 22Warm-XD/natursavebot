from __future__ import annotations

from datetime import timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import todo_keyboard
from src.db.repositories.reminders import create_reminder
from src.db.repositories.todos import list_todos, set_todo_status
from src.db.session import get_session


router = Router(name="todos")


@router.message(Command("todos"))
async def cmd_todos(message: Message) -> None:
    async with get_session() as session:
        todos = await list_todos(session)
    if not todos:
        await message.answer("Открытых задач пока нет.")
        return
    for todo in todos[:15]:
        deadline = todo.deadline_at.isoformat(sep=" ", timespec="minutes") if todo.deadline_at else "без дедлайна"
        await message.answer(f"<b>#{todo.id}</b> {todo.title}\nActor: {todo.actor or '-'}\nDeadline: <code>{deadline}</code>", reply_markup=todo_keyboard(todo.id))


@router.callback_query(lambda c: c.data and c.data.startswith("todo:"))
async def todo_callback(callback: CallbackQuery) -> None:
    _, action, raw_id = callback.data.split(":")
    todo_id = int(raw_id)
    async with get_session() as session:
        if action == "done":
            todo = await set_todo_status(session, todo_id, "done")
        elif action == "cancel":
            todo = await set_todo_status(session, todo_id, "cancelled")
        else:
            todo = await set_todo_status(session, todo_id, "open")
            if todo and todo.deadline_at:
                await create_reminder(session, text_value=todo.title, remind_at=todo.deadline_at + timedelta(hours=1))
        await session.commit()
    await callback.answer("Готово.")
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)

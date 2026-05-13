from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.db.repositories.messages import latest_deleted, latest_media
from src.db.repositories.save_mode import latest_events, stats
from src.db.repositories.settings import get_all_settings, set_setting
from src.db.session import get_session
from src.utils.text import clip, html_quote


router = Router(name="save_mode")


@router.message(Command("savemode"))
async def cmd_savemode(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or parts[1].lower() not in {"on", "off"}:
        await message.answer("Использование: /savemode on или /savemode off")
        return
    enabled = parts[1].lower() == "on"
    async with get_session() as session:
        await set_setting(session, "save_mode_enabled", enabled)
        await session.commit()
    await message.answer(f"SAVE MODE: {'on' if enabled else 'off'}.")


@router.message(Command("savemode_settings"))
async def cmd_savemode_settings(message: Message) -> None:
    async with get_session() as session:
        values = await get_all_settings(session)
    await message.answer(
        "<b>SAVE MODE</b>\n"
        f"Включён: <code>{values.get('save_mode_enabled')}</code>\n"
        f"Область: <code>{values.get('save_mode_scope')}</code>\n"
        f"Медиа: <code>{values.get('save_media_enabled')}</code>\n"
        f"Уведомлять об удалениях: <code>{values.get('save_mode_notify_deletes')}</code>\n"
        f"Уведомлять о правках: <code>{values.get('save_mode_notify_edits')}</code>\n"
        f"Максимум медиа: <code>{values.get('save_media_max_mb')}</code> MB\n\n"
        "Если в Telegram Business выбран режим только избранных чатов, Mnemora работает только с ними."
    )


@router.message(Command("savemode_stats"))
async def cmd_savemode_stats(message: Message) -> None:
    async with get_session() as session:
        values = await stats(session)
    if not values:
        await message.answer("SAVE MODE событий пока нет.")
        return
    await message.answer("<b>SAVE MODE stats</b>\n" + "\n".join(f"{key}: {value}" for key, value in values.items()))


@router.message(Command("deleted"))
async def cmd_deleted(message: Message) -> None:
    async with get_session() as session:
        rows = await latest_deleted(session)
    if not rows:
        await message.answer("Удалённых сообщений пока нет.")
        return
    await message.answer(
        "<b>Последние удаления</b>\n\n"
        + "\n\n".join(
            f"<code>{row.chat_id}/{row.message_id}</code> {html_quote(row.sender_name or '-')}: {html_quote(clip(row.text or row.caption or '', 220))}"
            for row in rows[:15]
        )
    )


@router.message(Command("edits"))
async def cmd_edits(message: Message) -> None:
    async with get_session() as session:
        rows = [
            row
            for row in await latest_events(session, None, limit=40)
            if row.kind in {"edit", "business_edit", "edit_untracked", "business_edit_untracked"}
        ]
    if not rows:
        await message.answer("Правок пока нет.")
        return
    await message.answer(
        "<b>Последние правки</b>\n\n"
        + "\n\n".join(
            f"<code>{row.chat_id}/{row.message_id}</code>\n"
            f"Было: {html_quote(clip(row.old_text or '', 160))}\n"
            f"Стало: {html_quote(clip(row.new_text or '', 160))}"
            for row in rows[:10]
        )
    )


@router.message(Command("media"))
async def cmd_media(message: Message) -> None:
    async with get_session() as session:
        rows = await latest_media(session)
    if not rows:
        await message.answer("Сохранённых медиа пока нет.")
        return
    await message.answer(
        "<b>Последние медиа</b>\n"
        + "\n".join(
            f"<code>{row.chat_id}/{row.message_id}</code> {row.media_type} · {row.media_status} · {html_quote(row.media_path or '-')}"
            for row in rows[:15]
        )
    )

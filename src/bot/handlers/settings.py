from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import settings_keyboard
from src.db.repositories.settings import get_all_settings, set_setting
from src.db.session import get_session
from src.services.llm.router import LLMRouter


router = Router(name="settings")


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    async with get_session() as session:
        values = await get_all_settings(session)
    await message.answer(
        _settings_text(values),
        reply_markup=settings_keyboard(
            provider=str(values["llm_provider"]),
            save_mode=bool(values["save_mode_enabled"]),
            autoreply=bool(values["auto_reply_enabled"]),
            digest=bool(values["digest_enabled"]),
        ),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("settings:"))
async def settings_callback(callback: CallbackQuery, llm: LLMRouter) -> None:
    action = callback.data.split(":", 1)[1]
    async with get_session() as session:
        values = await get_all_settings(session)
        if action == "provider":
            current = values.get("llm_provider", "anthropic")
            next_provider = {"openai": "gemini", "gemini": "anthropic", "anthropic": "openai"}[current]
            await set_setting(session, "llm_provider", next_provider)
            values["llm_provider"] = next_provider
            llm.settings.llm_provider = next_provider
        elif action == "toggle_save":
            values["save_mode_enabled"] = not bool(values["save_mode_enabled"])
            await set_setting(session, "save_mode_enabled", values["save_mode_enabled"])
        elif action == "toggle_auto":
            values["auto_reply_enabled"] = not bool(values["auto_reply_enabled"])
            await set_setting(session, "auto_reply_enabled", values["auto_reply_enabled"])
        elif action == "toggle_digest":
            values["digest_enabled"] = not bool(values["digest_enabled"])
            await set_setting(session, "digest_enabled", values["digest_enabled"])
        await session.commit()
    if not isinstance(callback.message, Message):
        await callback.answer("Открой /settings заново.", show_alert=True)
        return
    await callback.message.edit_text(
        _settings_text(values),
        reply_markup=settings_keyboard(
            provider=str(values["llm_provider"]),
            save_mode=bool(values["save_mode_enabled"]),
            autoreply=bool(values["auto_reply_enabled"]),
            digest=bool(values["digest_enabled"]),
        ),
    )
    await callback.answer()


@router.message(Command("autoreply"))
async def cmd_autoreply(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or parts[1].lower() not in {"on", "off"}:
        await message.answer("Использование: /autoreply on или /autoreply off")
        return
    enabled = parts[1].lower() == "on"
    async with get_session() as session:
        await set_setting(session, "auto_reply_enabled", enabled)
        await session.commit()
    await message.answer(f"Автоответчик: {'on' if enabled else 'off'}.")


def _settings_text(values: dict) -> str:
    return (
        "<b>Настройки</b>\n"
        f"LLM: <code>{values.get('llm_provider')}</code>\n"
        f"SAVE MODE: <code>{values.get('save_mode_enabled')}</code>\n"
        f"Область: <code>{values.get('save_mode_scope')}</code>\n"
        f"Медиа: <code>{values.get('save_media_enabled')}</code>, max {values.get('save_media_max_mb')} MB\n"
        f"Автоответчик: <code>{values.get('auto_reply_enabled')}</code> / <code>{values.get('auto_reply_mode')}</code>\n"
        f"Дайджест: <code>{values.get('digest_enabled')}</code> at <code>{values.get('digest_time')}</code>\n"
        f"Timezone: <code>{values.get('timezone')}</code>"
    )

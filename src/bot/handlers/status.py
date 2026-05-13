from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select, text

from src.business_bot.connection import latest_business_connection, rights_summary
from src.config import Settings
from src.db.models import Chat, DraftMessage, MediaFile, Message as StoredMessage
from src.db.repositories.settings import get_all_settings
from src.db.session import get_session
from src.userbot.client import UserbotManager


router = Router(name="status")


@router.message(Command("business_status", "status"))
async def cmd_business_status(message: Message, settings: Settings, userbot: UserbotManager) -> None:
    await message.answer(await build_business_status(settings, userbot))


@router.message(Command("health"))
async def cmd_health(message: Message, settings: Settings, userbot: UserbotManager) -> None:
    await message.answer(await build_health_status(settings, userbot))


async def build_business_status(settings: Settings, userbot: UserbotManager) -> str:
    async with get_session() as session:
        values = await get_all_settings(session)
        connection = await latest_business_connection(session, enabled_only=False)
        chat_count = await _count(session, Chat)
        message_count = await _count(session, StoredMessage)
        media_count = await _count(session, MediaFile)
        pending_drafts = await _count_where(session, DraftMessage, DraftMessage.status == "pending")

    userbot_client = userbot.get_client()
    userbot_state = "connected" if userbot_client and userbot_client.is_connected() else "off"
    return (
        "<b>Telegram Business</b>\n"
        f"Mode: <code>{settings.telegram_mode}</code>\n"
        f"{rights_summary(connection)}\n\n"
        "<b>Локальная база</b>\n"
        f"Чаты: <code>{chat_count}</code>\n"
        f"Сообщения: <code>{message_count}</code>\n"
        f"Медиа: <code>{media_count}</code>\n"
        f"Черновики: <code>{pending_drafts}</code>\n\n"
        "<b>Настройки</b>\n"
        f"SAVE MODE: <code>{values.get('save_mode_enabled')}</code>\n"
        f"Save media: <code>{values.get('save_media_enabled')}</code>\n"
        f"Notify deletes: <code>{values.get('save_mode_notify_deletes')}</code>\n"
        f"Notify edits: <code>{values.get('save_mode_notify_edits')}</code>\n"
        f"Legacy userbot: <code>{userbot_state}</code>"
    )


async def build_health_status(settings: Settings, userbot: UserbotManager) -> str:
    db_status = "ok"
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
            connection = await latest_business_connection(session, enabled_only=False)
    except Exception as exc:
        db_status = f"error: {type(exc).__name__}"
        connection = None

    provider = settings.llm_provider
    provider_key = {
        "openai": bool(settings.secret_value(settings.openai_api_key)),
        "gemini": bool(settings.secret_value(settings.gemini_api_key)),
        "anthropic": bool(settings.secret_value(settings.anthropic_api_key)),
    }.get(provider, False)
    userbot_client = userbot.get_client()
    userbot_state = "connected" if userbot_client and userbot_client.is_connected() else "off"
    media_ok = settings.media_dir.exists()
    return (
        "<b>Health</b>\n"
        f"База данных: <code>{db_status}</code>\n"
        f"Media dir: <code>{'ok' if media_ok else 'missing'}</code>\n"
        f"Business connected: <code>{bool(connection and connection.is_enabled)}</code>\n"
        f"Owner: <code>{'set' if settings.owner_telegram_id else 'missing'}</code>\n"
        f"LLM provider: <code>{provider}</code>\n"
        f"LLM key: <code>{'set' if provider_key else 'missing'}</code>\n"
        f"Legacy userbot: <code>{userbot_state}</code>"
    )


async def _count(session, model) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def _count_where(session, model, condition) -> int:
    return int((await session.execute(select(func.count()).select_from(model).where(condition))).scalar_one())

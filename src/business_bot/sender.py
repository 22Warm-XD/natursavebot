from __future__ import annotations

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.business_bot.connection import latest_business_connection
from src.config import Settings
from src.db.models import BusinessConnection, DraftMessage


async def send_business_draft(bot: Bot, session: AsyncSession, draft: DraftMessage, settings: Settings) -> None:
    connection = None
    if draft.business_connection_id:
        connection = (
            await session.execute(
                select(BusinessConnection).where(BusinessConnection.connection_id == draft.business_connection_id)
            )
        ).scalar_one_or_none()
    if connection is None:
        connection = await latest_business_connection(session)
    if connection is None or not connection.connection_id:
        raise RuntimeError("Telegram Business ещё не подключён.")
    if connection.user_id != settings.owner_telegram_id:
        raise RuntimeError("Business connection не принадлежит владельцу.")
    if not connection.is_enabled:
        raise RuntimeError("Business connection выключен в Telegram.")
    if connection.can_reply is False:
        raise RuntimeError("У бота нет права отвечать от имени Business-аккаунта.")
    await bot.send_message(draft.chat_id, draft.text, business_connection_id=connection.connection_id)

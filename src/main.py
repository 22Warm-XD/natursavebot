from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.bot.app import build_dispatcher
from src.bot.commands_menu import setup_bot_commands
from src.config import get_settings
from src.db.repositories.settings import get_all_settings
from src.db.session import init_db
from src.db.session import get_session
from src.logging_config import setup_logging
from src.services.agent import AgentRouter
from src.services.llm.router import LLMRouter
from src.services.reminders import ReminderScheduler
from src.userbot.client import UserbotManager


logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    settings.ensure_runtime_ready()
    settings.ensure_dirs()
    setup_logging()
    await init_db(settings.database_url)
    async with get_session() as session:
        persisted_settings = await get_all_settings(session)
    if persisted_settings.get("llm_provider"):
        settings.llm_provider = persisted_settings["llm_provider"]
    if persisted_settings.get("timezone"):
        settings.timezone = persisted_settings["timezone"]

    bot = Bot(token=settings.bot_token_value, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await setup_bot_commands(bot)
    llm = LLMRouter(settings)
    agent = AgentRouter(llm)
    userbot = UserbotManager(settings=settings, bot=bot, llm=llm)
    if settings.telegram_mode in {"userbot", "both"}:
        await userbot.restore()

    reminder_scheduler = ReminderScheduler(bot, settings, llm)
    reminder_scheduler.start()
    dp = build_dispatcher(settings, userbot, llm, agent)

    logger.info("Mnemora started")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=[
                "business_connection",
                "business_message",
                "edited_business_message",
                "deleted_business_messages",
                "message",
                "callback_query",
            ],
        )
    finally:
        await reminder_scheduler.shutdown()
        await userbot.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

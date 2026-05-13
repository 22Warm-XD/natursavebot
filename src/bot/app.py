from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.business_bot.handlers import router as business_router
from src.bot.filters import OwnerFilter
from src.bot.handlers import chat, digest, free_text, login, reminders, save_mode, search, send, settings, start, status, summary, todos
from src.config import Settings
from src.services.agent import AgentRouter
from src.services.llm.router import LLMRouter
from src.userbot.client import UserbotManager


def build_dispatcher(settings_obj: Settings, userbot: UserbotManager, llm: LLMRouter, agent: AgentRouter) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(business_router)
    owner_filter = OwnerFilter(settings_obj)
    dp.message.filter(owner_filter)
    dp.callback_query.filter(owner_filter)
    dp.workflow_data.update(settings=settings_obj, userbot=userbot, llm=llm, agent=agent)

    for router in (
        start.router,
        login.router,
        status.router,
        settings.router,
        search.router,
        chat.router,
        summary.router,
        todos.router,
        reminders.router,
        digest.router,
        send.router,
        save_mode.router,
        free_text.router,
    ):
        dp.include_router(router)
    return dp

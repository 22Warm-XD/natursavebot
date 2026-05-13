from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import BotCommand


logger = logging.getLogger(__name__)


COMMANDS = [
    BotCommand(command="start", description="подключение Telegram Business"),
    BotCommand(command="business_status", description="статус Business подключения"),
    BotCommand(command="health", description="проверка системы"),
    BotCommand(command="settings", description="настройки"),
    BotCommand(command="savemode", description="включить или выключить SAVE MODE"),
    BotCommand(command="savemode_settings", description="настройки SAVE MODE"),
    BotCommand(command="deleted", description="удалённые сообщения"),
    BotCommand(command="edits", description="правки сообщений"),
    BotCommand(command="media", description="сохранённые медиа"),
    BotCommand(command="search", description="поиск по локальной базе"),
    BotCommand(command="chat", description="карточка чата"),
    BotCommand(command="summary", description="выжимка чата"),
    BotCommand(command="catchup", description="где остановились"),
    BotCommand(command="todos", description="задачи и обещания"),
    BotCommand(command="remind", description="создать напоминание"),
    BotCommand(command="digest", description="дайджесты"),
    BotCommand(command="autoreply", description="автоответчик"),
    BotCommand(command="reply", description="черновик ответа"),
]


async def setup_bot_commands(bot: Bot) -> None:
    try:
        await bot.set_my_commands(COMMANDS)
    except Exception:
        logger.warning("failed to update bot command menu", exc_info=True)

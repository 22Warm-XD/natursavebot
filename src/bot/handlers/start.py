from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message


router = Router(name="start")


HELP_TEXT = """<b>Mnemora</b>
Telegram Business Save Mode & AI Assistant.

<b>Как подключить</b>
1. Открой Telegram.
2. Настройки -> Telegram Business.
3. Чат-боты / Автоматизация чатов.
4. Выбери этого бота.
5. Дай права на управление сообщениями и доступ к нужным личным чатам.
6. Вернись сюда и нажми /business_status.

<b>Система</b>
/business_status - статус Telegram Business
/health - проверка системы
/settings - настройки

<b>SAVE MODE</b>
/savemode on - включить SAVE MODE
/savemode off - выключить SAVE MODE
/savemode_settings - настройки
/deleted - удалённые сообщения
/edits - правки сообщений
/media - сохранённые медиа
/search текст - поиск
/chat имя - карточка чата

<b>AI-ассистент</b>
/summary чат - выжимка
/catchup чат - где остановились
/todos - задачи и обещания
/remind фраза - напоминание
/digest now - дайджест
/autoreply on/off - автоответчик

<b>Ответы</b>
/reply имя | текст - черновик ответа

<b>Dot-команды</b>
.mute, .unmute, .info, .type, .repeat, .love
Работают в Telegram Business mode в том же чате через business_connection_id.
Control-бот в ЛС нужен для настроек, логов и уведомлений SAVE MODE.

Отправка от имени Business-аккаунта всегда идёт через черновик и inline-подтверждение."""


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)

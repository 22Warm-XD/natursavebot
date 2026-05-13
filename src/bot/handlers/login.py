from __future__ import annotations

import re

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from telethon.errors import (
    ApiIdInvalidError,
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

from src.bot.states import LoginStates
from src.config import Settings
from src.db.repositories.settings import delete_telegram_credentials, save_telegram_credentials
from src.db.session import get_session
from src.userbot.client import UserbotManager


router = Router(name="login")


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext, userbot: UserbotManager) -> None:
    await userbot.cancel_pending(message.from_user.id)
    await state.clear()
    await message.answer("Отменено.")


@router.message(Command("logout"))
async def logout(message: Message, userbot: UserbotManager) -> None:
    await userbot.shutdown()
    async with get_session() as session:
        await delete_telegram_credentials(session)
        await session.commit()
    await message.answer("Legacy Telethon-сессия удалена из локальной базы.")


@router.message(Command("login"))
async def cmd_login(message: Message, state: FSMContext, settings: Settings) -> None:
    if settings.telegram_mode == "business":
        await message.answer(
            "Основной режим сейчас Telegram Business, /login не нужен.\n\n"
            "Подключение делается в Telegram: Настройки -> Telegram Business -> Чат-боты / Автоматизация чатов.\n"
            "Telethon-логин доступен только при TELEGRAM_MODE=userbot или TELEGRAM_MODE=both."
        )
        return
    await state.set_state(LoginStates.api_id)
    await message.answer("Legacy userbot: введи <code>api_id</code> с my.telegram.org.")


@router.message(LoginStates.api_id)
async def step_api_id(message: Message, state: FSMContext) -> None:
    try:
        api_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("api_id должен быть числом. Попробуй ещё раз или /cancel.")
        return
    await state.update_data(api_id=api_id)
    await state.set_state(LoginStates.api_hash)
    await message.answer("Теперь введи <code>api_hash</code>. Сообщение можно удалить после ввода.")


@router.message(LoginStates.api_hash)
async def step_api_hash(message: Message, state: FSMContext) -> None:
    api_hash = (message.text or "").strip()
    if not re.fullmatch(r"[a-fA-F0-9]{32}", api_hash):
        await message.answer("api_hash обычно состоит из 32 hex-символов. Проверь значение или /cancel.")
        return
    await state.update_data(api_hash=api_hash)
    await state.set_state(LoginStates.phone)
    await message.answer("Введи телефон в международном формате, например <code>+79991234567</code>.")


@router.message(LoginStates.phone)
async def step_phone(message: Message, state: FSMContext, userbot: UserbotManager) -> None:
    data = await state.get_data()
    phone = (message.text or "").strip()
    pending = userbot.start_pending(message.from_user.id, data["api_id"], data["api_hash"])
    pending.phone = phone
    try:
        await pending.client.connect()
        sent = await pending.client.send_code_request(phone)
        pending.phone_code_hash = sent.phone_code_hash
    except PhoneNumberInvalidError:
        await message.answer("Telegram не принял номер. Начни заново через /login.")
        await state.clear()
        return
    except ApiIdInvalidError:
        await message.answer("api_id/api_hash неверны. Начни заново через /login.")
        await state.clear()
        return
    except FloodWaitError as exc:
        await message.answer(f"FloodWait: подожди {exc.seconds} секунд.")
        await state.clear()
        return
    await state.set_state(LoginStates.code)
    await message.answer("Код отправлен. Введи его одним сообщением.")


@router.message(LoginStates.code)
async def step_code(message: Message, state: FSMContext, userbot: UserbotManager) -> None:
    pending = userbot.get_pending(message.from_user.id)
    if pending is None or not pending.phone:
        await message.answer("Сессия логина потерялась. Запусти /login заново.")
        await state.clear()
        return
    code = re.sub(r"\D", "", message.text or "")
    try:
        await pending.client.sign_in(pending.phone, code, phone_code_hash=pending.phone_code_hash)
    except SessionPasswordNeededError:
        await state.set_state(LoginStates.password)
        await message.answer("Нужен 2FA пароль. Введи пароль одним сообщением.")
        return
    except PhoneCodeInvalidError:
        await message.answer("Неверный код. Попробуй ещё раз или /cancel.")
        return
    except PhoneCodeExpiredError:
        await message.answer("Код истёк. Запусти /login заново.")
        await state.clear()
        return
    await _finalize_login(message, state, userbot)


@router.message(LoginStates.password)
async def step_password(message: Message, state: FSMContext, userbot: UserbotManager) -> None:
    pending = userbot.get_pending(message.from_user.id)
    if pending is None:
        await message.answer("Сессия логина потерялась. Запусти /login заново.")
        await state.clear()
        return
    try:
        await pending.client.sign_in(password=message.text or "")
    except Exception:
        await message.answer("Не удалось войти с этим 2FA паролем. Попробуй ещё раз или /cancel.")
        return
    await _finalize_login(message, state, userbot)


async def _finalize_login(message: Message, state: FSMContext, userbot: UserbotManager) -> None:
    pending = userbot.pop_pending(message.from_user.id)
    if pending is None:
        await message.answer("Не удалось завершить логин. Запусти /login заново.")
        await state.clear()
        return
    session_string = pending.client.session.save()
    async with get_session() as session:
        await save_telegram_credentials(session, pending.api_id, pending.api_hash, session_string)
        await session.commit()
    await userbot.register_client(pending.client)
    await state.clear()
    await message.answer("Готово. Legacy Telegram-аккаунт подключён, сессия сохранена зашифрованно.")

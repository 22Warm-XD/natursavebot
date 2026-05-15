from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from aiogram.types import Message

from src.business_bot.dot_commands import handle_business_dot_command
from src.business_bot.handlers import on_business_message
from src.config import Settings
from src.db.models import BusinessConnection
from src.db.repositories.chat_settings import get_chat_setting
from src.db.session import get_session, init_db


class _Bot:
    def __init__(self) -> None:
        self.sent_messages: list[dict] = []
        self.actions: list[dict] = []
        self.deleted: list[dict] = []

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)
        return kwargs

    async def send_chat_action(self, **kwargs):
        self.actions.append(kwargs)
        return True

    async def delete_business_messages(self, **kwargs):
        self.deleted.append(kwargs)
        return True


def _business_message(text: str, *, connection_id: str | None = "bc-1", reply: dict | None = None) -> Message:
    payload = {
        "message_id": 20,
        "date": 1778594400,
        "business_connection_id": connection_id,
        "chat": {"id": 500, "type": "private", "first_name": "Client"},
        "from": {"id": 100, "is_bot": False, "first_name": "Owner", "username": "owner"},
        "text": text,
    }
    if reply is not None:
        payload["reply_to_message"] = reply
    return Message.model_validate(payload)


async def _run(session: AsyncSession, message: Message, settings: Settings, bot: _Bot) -> bool:
    return await handle_business_dot_command(
        session,
        message=message,
        bot=bot,
        settings=settings,
    )


async def test_love_in_business_chat_sends_to_same_chat_not_owner_dm(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'dot-love.db'}")
    settings = Settings(
        _env_file=None,
        owner_telegram_id=100,
        telegram_mode="business",
        dot_command_cooldown_seconds=1,
        love_animation_max_messages=1,
    )
    bot = _Bot()
    message = _business_message(".love")

    async with get_session() as session:
        handled = await _run(session, message, settings, bot)
        await session.commit()

    assert handled is True
    assert bot.sent_messages
    assert all(call["chat_id"] == 500 for call in bot.sent_messages)
    assert not any(call["chat_id"] == 100 for call in bot.sent_messages)


async def test_type_sends_text_to_same_business_chat(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'dot-type.db'}")
    settings = Settings(_env_file=None, owner_telegram_id=100, telegram_mode="business")
    bot = _Bot()
    message = _business_message(".type Привет")

    async with get_session() as session:
        handled = await _run(session, message, settings, bot)
        await session.commit()

    assert handled is True
    assert any(call["text"] == "Привет" and call["chat_id"] == 500 for call in bot.sent_messages)


async def test_spam_repeat_sends_n_messages_to_same_chat(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'dot-repeat.db'}")
    settings = Settings(
        _env_file=None,
        owner_telegram_id=100,
        telegram_mode="business",
        max_repeat_count=5,
        repeat_delay_seconds=0.0,
        repeat_delay_min_seconds=0.0,
        repeat_delay_max_seconds=0.0,
        dot_command_cooldown_seconds=1,
    )
    bot = _Bot()
    message = _business_message(".spam 3 hi")

    async with get_session() as session:
        handled = await _run(session, message, settings, bot)
        await session.commit()
    await asyncio.sleep(0.4)

    assert handled is True
    sent_hi = [call for call in bot.sent_messages if call.get("text") == "hi" and call["chat_id"] == 500]
    assert len(sent_hi) == 3


async def test_info_reply_answers_in_same_chat(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'dot-info.db'}")
    settings = Settings(_env_file=None, owner_telegram_id=100, telegram_mode="business")
    bot = _Bot()
    reply = {
        "message_id": 7,
        "date": 1778594300,
        "chat": {"id": 500, "type": "private", "first_name": "Client"},
        "from": {"id": 42, "is_bot": False, "first_name": "Ivan", "username": "ivan"},
        "text": "hello",
    }
    message = _business_message(".info", reply=reply)

    async with get_session() as session:
        handled = await _run(session, message, settings, bot)
        await session.commit()

    assert handled is True
    info_calls = [call for call in bot.sent_messages if call["chat_id"] == 500 and "Информация о пользователе" in call["text"]]
    assert info_calls
    assert info_calls[0].get("reply_to_message_id") == 7


async def test_mute_reply_goes_to_same_chat_and_enables_hard_mute(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'dot-mute.db'}")
    settings = Settings(_env_file=None, owner_telegram_id=100, telegram_mode="business")
    bot = _Bot()
    message = _business_message(".mute")

    async with get_session() as session:
        handled = await _run(session, message, settings, bot)
        await session.commit()

    assert handled is True
    assert any(call["chat_id"] == 500 and "Hard mute включён" in call["text"] for call in bot.sent_messages)
    async with get_session() as session:
        row = await get_chat_setting(session, 500)
    assert row is not None
    assert row.hard_muted is True


async def test_missing_business_connection_id_does_not_crash(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'dot-no-conn.db'}")
    settings = Settings(_env_file=None, owner_telegram_id=100, telegram_mode="business")
    bot = _Bot()
    message = _business_message(".love", connection_id=None)

    async with get_session() as session:
        handled = await _run(session, message, settings, bot)
        await session.commit()

    assert handled is True
    assert any(call["chat_id"] == 100 for call in bot.sent_messages)


async def test_business_message_love_processed_by_business_router(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'dot-router-love.db'}")
    settings = Settings(
        _env_file=None,
        owner_telegram_id=100,
        telegram_mode="business",
        save_mode_enabled=False,
        dot_command_cooldown_seconds=0,
        love_animation_max_messages=1,
    )
    bot = _Bot()
    message = _business_message(".love", connection_id="bc-1")

    async with get_session() as session:
        session.add(
            BusinessConnection(
                connection_id="bc-1",
                user_id=100,
                is_enabled=True,
                can_reply=True,
            )
        )
        await session.commit()

    await on_business_message(message, bot, settings)

    assert any(call["chat_id"] == 500 for call in bot.sent_messages)
    assert not any(call["chat_id"] == 100 for call in bot.sent_messages)

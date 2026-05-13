from __future__ import annotations

import pytest
from sqlalchemy import select

from src.config import Settings
from src.db.models import HardMuteEvent
from src.db.repositories.chat_settings import get_chat_setting, hard_mute_active, set_hard_mute
from src.db.repositories.hard_mute import create_hard_mute_event, update_hard_mute_delete_status
from src.db.session import get_session, init_db
from src.services.hard_mute import (
    DotCommandCooldown,
    clamp_repeat_count,
    delete_hard_muted_message,
    dot_usage,
    parse_repeat_args,
)


async def test_mute_and_unmute_toggle_chat_setting(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'hard-mute.db'}")

    async with get_session() as session:
        row = await set_hard_mute(session, chat_id=10, enabled=True, chat_title="Client", username="client")
        await session.commit()

    assert row.hard_muted is True
    assert row.hard_muted_at is not None
    assert hard_mute_active(row) is True

    async with get_session() as session:
        row = await set_hard_mute(session, chat_id=10, enabled=False)
        await session.commit()

    assert row.hard_muted is False
    assert hard_mute_active(row) is False
    async with get_session() as session:
        stored = await get_chat_setting(session, 10)

    assert stored is not None
    assert stored.chat_id == 10


async def test_hard_muted_message_creates_event_and_saves_delete_error(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'hard-event.db'}")

    async with get_session() as session:
        event = await create_hard_mute_event(
            session,
            chat_id=10,
            message_id=20,
            sender_id=30,
            sender_name="Client",
            sender_username="client",
            text="secret",
            media_file_id=None,
            media_local_path=None,
            raw_json='{"ok": true}',
        )
        await update_hard_mute_delete_status(
            session,
            event,
            delete_for_everyone_success=False,
            delete_local_success=True,
            delete_error="MESSAGE_DELETE_FORBIDDEN",
        )
        await session.commit()

    async with get_session() as session:
        stored = (await session.execute(select(HardMuteEvent))).scalar_one()

    assert stored.text == "secret"
    assert stored.delete_for_everyone_success is False
    assert stored.delete_local_success is True
    assert stored.delete_error == "MESSAGE_DELETE_FORBIDDEN"


class _DeleteClient:
    def __init__(self, fail_revoke: bool = False) -> None:
        self.fail_revoke = fail_revoke
        self.calls: list[tuple[int, tuple[int, ...], bool]] = []

    async def delete_messages(self, chat_id: int, ids: list[int], *, revoke: bool) -> None:
        self.calls.append((chat_id, tuple(ids), revoke))
        if revoke and self.fail_revoke:
            raise RuntimeError("delete forbidden")


async def test_delete_for_everyone_success_calls_telethon_revoke() -> None:
    client = _DeleteClient()

    result = await delete_hard_muted_message(client, chat_id=10, message_id=20, delete_for_everyone=True)

    assert result.delete_for_everyone_success is True
    assert result.delete_local_success is True
    assert client.calls == [(10, (20,), True)]


async def test_delete_for_everyone_failure_falls_back_to_local_delete() -> None:
    client = _DeleteClient(fail_revoke=True)

    result = await delete_hard_muted_message(client, chat_id=10, message_id=20, delete_for_everyone=True)

    assert result.delete_for_everyone_success is False
    assert result.delete_local_success is True
    assert "delete forbidden" in (result.delete_error or "")
    assert client.calls == [(10, (20,), True), (10, (20,), False)]


def test_repeat_limits_usage_and_cooldown() -> None:
    settings = Settings(_env_file=None, max_repeat_count=5)

    assert parse_repeat_args("100 привет") == (100, "привет")
    assert parse_repeat_args("привет") == (None, None)
    assert dot_usage(".repeat") == "Usage: .repeat 5 привет"
    assert clamp_repeat_count(100, settings) == (5, True)

    cooldown = DotCommandCooldown()
    assert cooldown.check(1, "repeat", now=100.0, cooldown_seconds=30) == 0
    assert cooldown.check(1, "repeat", now=110.0, cooldown_seconds=30) == pytest.approx(20)

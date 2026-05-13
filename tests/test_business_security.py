from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.filters import OwnerFilter
from src.business_bot.sender import send_business_draft
from src.config import Settings
from src.db.models import BusinessConnection, DraftMessage
from src.db.session import get_session, init_db


class _Event:
    def __init__(self, user_id: int) -> None:
        self.from_user = type("User", (), {"id": user_id})()


class _Bot:
    async def send_message(self, *args, **kwargs) -> None:
        raise AssertionError("send_message must not be called when can_reply is false")


async def test_owner_filter_rejects_non_owner() -> None:
    owner_filter = OwnerFilter(Settings(_env_file=None, owner_telegram_id=100))

    assert await owner_filter(_Event(100)) is True
    assert await owner_filter(_Event(200)) is False


async def test_business_sender_requires_can_reply(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'sender.db'}")
    settings = Settings(_env_file=None, owner_telegram_id=100)

    async with get_session() as session:
        session.add(
            BusinessConnection(
                connection_id="bc-1",
                user_id=100,
                is_enabled=True,
                can_reply=False,
            )
        )
        draft = DraftMessage(
            id="draft-1",
            business_connection_id="bc-1",
            chat_id=500,
            recipient_label="Client",
            text="hello",
        )
        session.add(draft)
        await session.commit()

    async with get_session() as session:
        draft = await session.get(DraftMessage, "draft-1")
        assert draft is not None
        with pytest.raises(RuntimeError, match="нет права"):
            await send_business_draft(_Bot(), session, draft, settings)

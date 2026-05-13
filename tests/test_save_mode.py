from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from src.db.models import EditHistory, SaveModeEvent
from src.db.repositories.messages import get_message, upsert_message
from src.db.session import get_session, init_db
from src.services.save_mode import record_delete, record_edit, record_media_unavailable


async def test_save_mode_records_edit_and_delete(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    async with get_session() as session:
        await upsert_message(
            session,
            chat_id=100,
            message_id=5,
            sender_id=7,
            sender_name="Oleg",
            sender_username="oleg",
            chat_title="Oleg",
            direction="incoming",
            text_value="old",
            date=datetime(2026, 5, 12, 10, 0),
        )
        await session.commit()

    async with get_session() as session:
        note = await record_edit(session, chat_id=100, message_id=5, new_text="new", edited_at=datetime(2026, 5, 12, 10, 5))
        await session.commit()
        assert note is not None

    async with get_session() as session:
        message = await get_message(session, 100, 5)
        edits = list((await session.execute(select(EditHistory))).scalars())
        assert message is not None
        assert message.text == "new"
        assert len(edits) == 1
        assert edits[0].old_text == "old"

    async with get_session() as session:
        notes = await record_delete(session, message_ids=[5], chat_id=100, deleted_at=datetime(2026, 5, 12, 10, 10))
        await session.commit()
        assert len(notes) == 1

    async with get_session() as session:
        message = await get_message(session, 100, 5)
        events = list((await session.execute(select(SaveModeEvent).order_by(SaveModeEvent.id))).scalars())
        assert message is not None
        assert message.deleted is True
        assert [event.kind for event in events] == ["edit", "delete"]


async def test_save_mode_edge_cases(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'edge.db'}")

    async with get_session() as session:
        untracked = await record_edit(session, chat_id=200, message_id=1, new_text="new")
        unknown_deletes = await record_delete(session, message_ids=[404], chat_id=200)
        media_event = await record_media_unavailable(
            session,
            chat_id=200,
            message_id=2,
            sender_id=9,
            sender_name="Ann",
            media_type="photo",
            status="protected",
        )
        await session.commit()

    assert untracked is not None
    assert untracked.kind == "edit_untracked"
    assert unknown_deletes == []
    assert media_event.kind == "media_unavailable"

    async with get_session() as session:
        await upsert_message(
            session,
            chat_id=200,
            message_id=3,
            sender_id=9,
            sender_name="Ann",
            sender_username="ann",
            chat_title="Ann",
            direction="incoming",
            text_value="same",
            date=datetime(2026, 5, 12, 10, 0),
        )
        await session.commit()

    async with get_session() as session:
        note = await record_edit(session, chat_id=200, message_id=3, new_text="same")
        filtered = await record_delete(session, message_ids=[3], chat_id=None, allowed_chat_ids={999})
        await session.commit()

    assert note is None
    assert filtered == []

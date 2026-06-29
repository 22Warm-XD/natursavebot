from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from aiogram.types import Update
from sqlalchemy import select

from src.business_bot.media_downloader import BusinessMedia, extract_business_media, has_expiring_media_hint
from src.db.models import BusinessConnection, DeletedEvent, EditHistory, MediaFile, Message, MessageEdit, SaveModeEvent
from src.business_bot.message_saver import save_business_delete, save_business_message
from src.db.repositories.messages import get_message, upsert_message
from src.db.session import get_session, init_db
from src.services.save_mode_business import record_business_update


def _message(text: str, *, message_id: int = 10) -> dict:
    return {
        "message_id": message_id,
        "date": 1778594400,
        "business_connection_id": "bc-1",
        "chat": {"id": 500, "type": "private", "first_name": "Client"},
        "from": {"id": 42, "is_bot": False, "first_name": "Client", "username": "client"},
        "text": text,
    }


async def test_business_update_raw_flow_saves_connection_message_edit_and_deletes(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'business.db'}")
    async with get_session() as session:
        notes = await record_business_update(
            session,
            {
                "update_id": 1,
                "business_connection": {
                    "id": "bc-1",
                    "user": {"id": 42, "is_bot": False, "first_name": "Client", "username": "client"},
                    "user_chat_id": 500,
                    "date": 1778594400,
                    "is_enabled": True,
                    "can_reply": True,
                },
            },
        )
        await session.commit()
    assert [note.kind for note in notes] == ["business_connection"]

    async with get_session() as session:
        notes = await record_business_update(
            session,
            {
                "update_id": 2,
                "business_message": {
                    **_message("old"),
                    "photo": [
                        {"file_id": "small", "file_unique_id": "s", "width": 10, "height": 10, "file_size": 100},
                        {"file_id": "big", "file_unique_id": "b", "width": 100, "height": 100, "file_size": 1000},
                    ],
                },
            },
        )
        await session.commit()
    assert [note.kind for note in notes] == ["business_message"]

    async with get_session() as session:
        notes = await record_business_update(
            session,
            {
                "update_id": 3,
                "edited_business_message": {
                    **_message("new"),
                    "caption": "new caption",
                    "edit_date": 1778598000,
                },
            },
        )
        await session.commit()
    assert [note.kind for note in notes] == ["business_edit"]

    async with get_session() as session:
        notes = await record_business_update(
            session,
            {
                "update_id": 4,
                "deleted_business_messages": {
                    "business_connection_id": "bc-1",
                    "chat": {"id": 500, "type": "private"},
                    "message_ids": [10, 404],
                },
            },
        )
        await session.commit()
    assert [note.kind for note in notes] == ["business_delete", "business_delete"]

    async with get_session() as session:
        connection = (await session.execute(select(BusinessConnection))).scalar_one()
        message = (await session.execute(select(Message))).scalar_one()
        edits = list((await session.execute(select(EditHistory))).scalars())
        message_edits = list((await session.execute(select(MessageEdit))).scalars())
        deleted_events = list((await session.execute(select(DeletedEvent))).scalars())
        events = list((await session.execute(select(SaveModeEvent).order_by(SaveModeEvent.id))).scalars())

    assert connection.connection_id == "bc-1"
    assert connection.user_chat_id == 500
    assert connection.raw_json
    assert message.source == "business"
    assert message.is_business is True
    assert message.business_connection_id == "bc-1"
    assert message.text == "new"
    assert message.caption == "new caption"
    assert message.raw_json
    assert message.deleted is True
    assert message.deleted_at is not None
    assert message.media_type == "photo"
    assert json.loads(message.media_meta_json)["selected"]["file_id"] == "big"
    assert len(edits) == 1
    assert edits[0].old_text == "old"
    assert edits[0].edited_at == datetime(2026, 5, 12, 15, 0)
    assert len(message_edits) == 1
    assert message_edits[0].raw_json
    assert len(deleted_events) == 1
    assert deleted_events[0].found_count == 1
    assert json.loads(deleted_events[0].message_ids_json) == [10, 404]
    assert [event.kind for event in events] == [
        "business_connection",
        "business_message",
        "business_edit",
        "business_delete",
        "business_delete",
    ]
    assert events[-1].message_id == 404


async def test_business_update_accepts_aiogram_typed_update(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'typed.db'}")
    update = Update.model_validate({"update_id": 5, "business_message": _message("typed", message_id=11)})

    async with get_session() as session:
        notes = await record_business_update(session, update)
        await session.commit()

    assert [note.kind for note in notes] == ["business_message"]
    async with get_session() as session:
        row = (await session.execute(select(Message))).scalar_one()

    assert row.chat_id == 500
    assert row.message_id == 11
    assert row.date == datetime(2026, 5, 12, 14, 0)


async def test_typed_delete_ignores_owner_messages(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'owner-delete.db'}")

    async with get_session() as session:
        await upsert_message(
            session,
            source="business",
            is_business=True,
            business_connection_id="bc-1",
            chat_id=500,
            message_id=20,
            sender_id=100,
            sender_name="Owner",
            sender_username="owner",
            chat_title="Client",
            direction="outgoing",
            text_value="my message",
            date=datetime(2026, 5, 12, 14, 0),
        )
        await session.commit()

    deleted = SimpleNamespace(
        business_connection_id="bc-1",
        chat=SimpleNamespace(id=500),
        message_ids=[20],
        model_dump_json=lambda exclude_none=True: "{}",
    )
    async with get_session() as session:
        messages, event = await save_business_delete(session, deleted, owner_id=100)
        await session.commit()

    assert messages == []
    assert event is not None
    assert event.found_count == 1
    async with get_session() as session:
        row = (await session.execute(select(Message))).scalar_one()
        events = list((await session.execute(select(SaveModeEvent))).scalars())

    assert row.deleted is True
    assert row.deleted_at is not None
    assert len(events) == 1
    assert events[0].kind == "delete"
    assert events[0].message_id == 20


async def test_business_messages_are_scoped_by_connection_id(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'connections.db'}")

    async with get_session() as session:
        for connection_id, text in (("bc-1", "first"), ("bc-2", "second")):
            await upsert_message(
                session,
                source="business",
                is_business=True,
                business_connection_id=connection_id,
                chat_id=500,
                message_id=20,
                sender_id=42,
                sender_name="Client",
                sender_username="client",
                chat_title="Client",
                direction="incoming",
                text_value=text,
                date=datetime(2026, 5, 12, 14, 0),
            )
        await session.commit()

    async with get_session() as session:
        rows = list((await session.execute(select(Message).order_by(Message.business_connection_id))).scalars())
        first = await get_message(session, 500, 20, source="business", business_connection_id="bc-1")
        second = await get_message(session, 500, 20, source="business", business_connection_id="bc-2")

    assert [row.business_connection_id for row in rows] == ["bc-1", "bc-2"]
    assert first is not None and first.text == "first"
    assert second is not None and second.text == "second"


async def test_business_media_upsert_does_not_duplicate_rows(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'media-dedupe.db'}")
    message = Update.model_validate({"update_id": 7, "business_message": _message("photo", message_id=31)}).business_message
    assert message is not None
    media = BusinessMedia(
        media_type="photo",
        file_id="file-1",
        file_unique_id="unique-1",
        file_size=100,
        width=10,
        height=10,
        status="metadata_only",
        metadata={"file_id": "file-1"},
    )

    async with get_session() as session:
        await save_business_message(session, message, media, owner_id=100)
        await save_business_message(session, message, media, owner_id=100)
        await session.commit()

    async with get_session() as session:
        rows = list((await session.execute(select(MediaFile))).scalars())

    assert len(rows) == 1
    assert rows[0].file_unique_id == "unique-1"


async def test_typed_business_message_dates_are_saved_as_naive_utc(tmp_path) -> None:
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'typed-date.db'}")
    message = Update.model_validate(
        {
            "update_id": 8,
            "business_message": {
                **_message("date", message_id=32),
                "date": datetime(2026, 5, 12, 19, 0, tzinfo=timezone(timedelta(hours=5))),
            },
        }
    ).business_message
    assert message is not None

    async with get_session() as session:
        await save_business_message(session, message, owner_id=100)
        await session.commit()

    async with get_session() as session:
        row = (await session.execute(select(Message))).scalar_one()

    assert row.date == datetime(2026, 5, 12, 14, 0)
    assert row.date.tzinfo is None


def test_expiring_media_hint_detects_raw_payload_markers() -> None:
    message = SimpleNamespace(
        text=None,
        caption=None,
        has_media_spoiler=False,
        model_dump=lambda mode="json", by_alias=True, exclude_none=True: {"media": {"viewOnce": True}},
    )

    assert has_expiring_media_hint(message) is True


def test_business_voice_audio_are_ignored_unless_reply_save_allows_them() -> None:
    voice_message = Update.model_validate(
        {
            "update_id": 6,
            "business_message": {
                **_message("voice", message_id=30),
                "voice": {"file_id": "voice-id", "file_unique_id": "voice-uid", "duration": 3, "file_size": 1000},
            },
        }
    ).business_message

    assert voice_message is not None
    assert extract_business_media(voice_message).media_type is None
    assert extract_business_media(voice_message, allow_voice_audio=True).media_type == "voice"

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import HardMuteEvent


async def create_hard_mute_event(
    session: AsyncSession,
    *,
    chat_id: int,
    message_id: int,
    sender_id: int | None,
    sender_name: str | None,
    sender_username: str | None,
    text: str | None,
    media_file_id: str | None,
    media_local_path: str | None,
    raw_json: str | None,
) -> HardMuteEvent:
    event = HardMuteEvent(
        chat_id=chat_id,
        message_id=message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        sender_username=sender_username,
        text=text,
        media_file_id=media_file_id,
        media_local_path=media_local_path,
        raw_json=raw_json,
    )
    session.add(event)
    await session.flush()
    return event


async def update_hard_mute_delete_status(
    session: AsyncSession,
    event: HardMuteEvent,
    *,
    delete_for_everyone_success: bool,
    delete_local_success: bool,
    delete_error: str | None,
) -> HardMuteEvent:
    event.delete_for_everyone_success = delete_for_everyone_success
    event.delete_local_success = delete_local_success
    event.delete_error = delete_error
    await session.flush()
    return event

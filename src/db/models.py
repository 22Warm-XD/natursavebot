from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TelegramCredential(Base):
    __tablename__ = "telegram_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    api_id: Mapped[int] = mapped_column(Integer)
    api_hash_enc: Mapped[str] = mapped_column(Text)
    session_string_enc: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class SecretValue(Base):
    __tablename__ = "secret_values"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_enc: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(512), index=True)
    username: Mapped[str | None] = mapped_column(String(255), index=True)
    chat_type: Mapped[str] = mapped_column(String(32), default="unknown")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    muted_project: Mapped[bool] = mapped_column(Boolean, default=False)
    whitelisted: Mapped[bool] = mapped_column(Boolean, default=False)
    blacklisted: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ChatSetting(Base):
    __tablename__ = "chat_settings"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_title: Mapped[str | None] = mapped_column(String(512))
    username: Mapped[str | None] = mapped_column(String(255), index=True)
    hard_muted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    hard_muted_at: Mapped[datetime | None] = mapped_column(DateTime)
    hard_muted_until: Mapped[datetime | None] = mapped_column(DateTime)
    hard_mute_delete_for_everyone: Mapped[bool] = mapped_column(Boolean, default=True)
    save_mode_enabled: Mapped[bool | None] = mapped_column(Boolean)
    notify_enabled: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class BusinessConnection(Base):
    __tablename__ = "business_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    user_name: Mapped[str | None] = mapped_column(String(512))
    user_username: Mapped[str | None] = mapped_column(String(255), index=True)
    user_chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    date: Mapped[datetime | None] = mapped_column(DateTime)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    can_reply: Mapped[bool | None] = mapped_column(Boolean)
    rights_json: Mapped[str | None] = mapped_column(Text)
    allowed_chats_mode: Mapped[str | None] = mapped_column(String(64))
    raw_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("chat_id", "message_id", name="uq_message_chat_msg"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default="telethon", index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int] = mapped_column(Integer, index=True)
    sender_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    sender_name: Mapped[str | None] = mapped_column(String(512))
    sender_username: Mapped[str | None] = mapped_column(String(255))
    chat_title: Mapped[str | None] = mapped_column(String(512))
    direction: Mapped[str] = mapped_column(String(16), default="incoming")
    business_connection_id: Mapped[str | None] = mapped_column(String(255), index=True)
    is_business: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    text: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    date: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime)
    reply_to: Mapped[int | None] = mapped_column(Integer)
    media_type: Mapped[str | None] = mapped_column(String(64))
    media_path: Mapped[str | None] = mapped_column(Text)
    media_status: Mapped[str | None] = mapped_column(String(32))
    media_meta_json: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[str | None] = mapped_column(Text)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    edits: Mapped[list["EditHistory"]] = relationship(back_populates="message", cascade="all, delete-orphan")


class EditHistory(Base):
    __tablename__ = "edit_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_db_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int] = mapped_column(Integer, index=True)
    old_text: Mapped[str | None] = mapped_column(Text)
    new_text: Mapped[str | None] = mapped_column(Text)
    edited_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    message: Mapped[Message | None] = relationship(back_populates="edits")


class MessageEdit(Base):
    __tablename__ = "message_edits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_db_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(32), default="business", index=True)
    business_connection_id: Mapped[str | None] = mapped_column(String(255), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int] = mapped_column(Integer, index=True)
    old_text: Mapped[str | None] = mapped_column(Text)
    new_text: Mapped[str | None] = mapped_column(Text)
    edited_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    raw_json: Mapped[str | None] = mapped_column(Text)


class DeletedEvent(Base):
    __tablename__ = "deleted_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default="business", index=True)
    business_connection_id: Mapped[str | None] = mapped_column(String(255), index=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    message_ids_json: Mapped[str] = mapped_column(Text)
    found_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_db_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    source: Mapped[str] = mapped_column(String(32), default="business", index=True)
    business_connection_id: Mapped[str | None] = mapped_column(String(255), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int] = mapped_column(Integer, index=True)
    media_type: Mapped[str] = mapped_column(String(64))
    file_id: Mapped[str | None] = mapped_column(Text)
    file_unique_id: Mapped[str | None] = mapped_column(String(255))
    file_size: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    duration: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    local_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="metadata")
    error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class HardMuteEvent(Base):
    __tablename__ = "hard_mute_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int] = mapped_column(Integer, index=True)
    sender_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    sender_name: Mapped[str | None] = mapped_column(String(512))
    sender_username: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str | None] = mapped_column(Text)
    media_file_id: Mapped[str | None] = mapped_column(Text)
    media_local_path: Mapped[str | None] = mapped_column(Text)
    delete_for_everyone_success: Mapped[bool] = mapped_column(Boolean, default=False)
    delete_local_success: Mapped[bool] = mapped_column(Boolean, default=False)
    delete_error: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    actor: Mapped[str | None] = mapped_column(String(512))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    source_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    remind_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    lead_minutes: Mapped[int | None] = mapped_column(Integer)
    last_ping_at: Mapped[datetime | None] = mapped_column(DateTime)
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    message_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="summary")
    text: Mapped[str] = mapped_column(Text)
    from_date: Mapped[datetime | None] = mapped_column(DateTime)
    to_date: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class SaveModeEvent(Base):
    __tablename__ = "save_mode_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int | None] = mapped_column(Integer)
    business_connection_id: Mapped[str | None] = mapped_column(String(255), index=True)
    sender_id: Mapped[int | None] = mapped_column(BigInteger)
    sender_name: Mapped[str | None] = mapped_column(String(512))
    text: Mapped[str | None] = mapped_column(Text)
    old_text: Mapped[str | None] = mapped_column(Text)
    new_text: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String(64))
    media_path: Mapped[str | None] = mapped_column(Text)
    media_status: Mapped[str | None] = mapped_column(String(32))
    payload_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class DraftMessage(Base):
    __tablename__ = "draft_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_connection_id: Mapped[str | None] = mapped_column(String(255), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    recipient_label: Mapped[str] = mapped_column(String(512))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

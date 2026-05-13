from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "Mnemora"

    bot_token: SecretStr | str = ""
    owner_telegram_id: int = 0
    encryption_key: str = ""

    timezone: str = "Europe/Moscow"
    telegram_mode: Literal["business", "userbot", "both"] = "business"
    database_url: str = "sqlite+aiosqlite:///data/app.db"
    data_dir: Path = Path("data")
    media_dir: Path = Path("data/media")

    ignore_archived_chats: bool = True
    sync_dialog_limit: int = 50
    sync_messages_per_chat: int = 40

    llm_provider: Literal["openai", "gemini", "anthropic"] = "anthropic"
    max_context_messages: int = 80
    max_summary_chars: int = 3000
    max_llm_input_chars: int = 12000
    daily_llm_limit: int = 100

    openai_api_key: SecretStr | str = ""
    openai_model: str = "gpt-4o-mini"
    openai_transcribe_model: str = "whisper-1"
    gemini_api_key: SecretStr | str = ""
    gemini_model: str = "gemini-1.5-flash"
    anthropic_api_key: SecretStr | str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"

    save_mode_enabled: bool = True
    save_mode_scope: Literal["private", "private_and_groups"] = "private"
    save_media_enabled: bool = True
    save_mode_notify_deletes: bool = True
    save_mode_notify_edits: bool = True
    save_media_max_mb: int = 50
    max_media_size_mb: int | None = None
    notify_deletes: bool | None = None
    notify_edits: bool | None = None

    auto_reply_enabled: bool = False
    auto_reply_mode: Literal["static", "smart"] = "static"
    auto_reply_text: str = "Сейчас не могу ответить, напишу позже."
    auto_reply_cooldown_seconds: int = 900

    reminder_lead_minutes: list[int] = Field(default_factory=lambda: [15, 60, 240, 1440])
    digest_enabled: bool = False
    digest_time: str = "09:00"

    enable_dot_commands: bool = True
    enable_hard_mute: bool = True
    hard_mute_delete_for_everyone: bool = True
    enable_group_hard_mute: bool = False
    enable_spam_alias: bool = True
    max_repeat_count: int = 5
    repeat_delay_seconds: float = 1.0
    enable_group_repeat: bool = False
    dot_command_cooldown_seconds: int = 30
    type_max_text_length: int = 4096
    love_animation_max_messages: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("reminder_lead_minutes", mode="before")
    @classmethod
    def parse_lead_minutes(cls, value: object) -> list[int]:
        if isinstance(value, str):
            normalized = value.strip().strip("[]")
            return [int(item.strip()) for item in normalized.split(",") if item.strip()]
        if isinstance(value, list):
            return [int(item) for item in value]
        return [15, 60, 240, 1440]

    def secret_value(self, value: SecretStr | str) -> str:
        if isinstance(value, SecretStr):
            return value.get_secret_value()
        return value

    @property
    def bot_token_value(self) -> str:
        return self.secret_value(self.bot_token)

    def ensure_runtime_ready(self) -> None:
        missing: list[str] = []
        if not self.bot_token_value:
            missing.append("BOT_TOKEN")
        if not self.owner_telegram_id:
            missing.append("OWNER_TELEGRAM_ID")
        if not self.encryption_key:
            missing.append("ENCRYPTION_KEY")
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(f"Missing required environment values: {joined}")

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)

    @property
    def effective_save_media_max_mb(self) -> int:
        return self.max_media_size_mb or self.save_media_max_mb

    @property
    def effective_notify_deletes(self) -> bool:
        return self.save_mode_notify_deletes if self.notify_deletes is None else self.notify_deletes

    @property
    def effective_notify_edits(self) -> bool:
        return self.save_mode_notify_edits if self.notify_edits is None else self.notify_edits


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from aiogram import Bot
from telethon import TelegramClient
from telethon.sessions import StringSession

from src.config import Settings
from src.db.repositories.settings import load_telegram_credentials
from src.db.session import get_session
from src.services.llm.router import LLMRouter
from src.userbot.commands import attach_user_commands
from src.userbot.events import attach_event_handlers


logger = logging.getLogger(__name__)


@dataclass
class PendingLogin:
    client: TelegramClient
    api_id: int
    api_hash: str
    phone: str | None = None
    phone_code_hash: str | None = None


@dataclass
class UserbotManager:
    settings: Settings
    bot: Bot
    llm: LLMRouter
    _client: TelegramClient | None = None
    _pending: dict[int, PendingLogin] = field(default_factory=dict)
    _handlers_attached: set[int] = field(default_factory=set)

    def get_client(self) -> TelegramClient | None:
        return self._client

    async def restore(self) -> None:
        async with get_session() as session:
            creds = await load_telegram_credentials(session)
        if creds is None:
            return
        api_id, api_hash, session_string = creds
        client = TelegramClient(StringSession(session_string), api_id, api_hash)
        await client.connect()
        if await client.is_user_authorized():
            await self.register_client(client)
            logger.info("Telethon session restored")
        else:
            await client.disconnect()
            logger.warning("Stored Telethon session is not authorized")

    async def register_client(self, client: TelegramClient) -> None:
        if self._client is not None and self._client is not client:
            try:
                await self._client.disconnect()
            except Exception:
                logger.exception("Failed to disconnect previous Telethon client")
        if not client.is_connected():
            await client.connect()
        self._client = client
        marker = id(client)
        if marker not in self._handlers_attached:
            attach_user_commands(client, self.settings.owner_telegram_id, self.settings)
            attach_event_handlers(client, self.bot, self.settings, self.llm, self.settings.owner_telegram_id)
            self._handlers_attached.add(marker)

    def start_pending(self, owner_id: int, api_id: int, api_hash: str) -> PendingLogin:
        pending = PendingLogin(client=TelegramClient(StringSession(), api_id, api_hash), api_id=api_id, api_hash=api_hash)
        self._pending[owner_id] = pending
        return pending

    def get_pending(self, owner_id: int) -> PendingLogin | None:
        return self._pending.get(owner_id)

    def pop_pending(self, owner_id: int) -> PendingLogin | None:
        return self._pending.pop(owner_id, None)

    async def cancel_pending(self, owner_id: int) -> None:
        pending = self._pending.pop(owner_id, None)
        if pending:
            await pending.client.disconnect()

    async def shutdown(self) -> None:
        if self._client:
            await self._client.disconnect()
            self._client = None
        for pending in list(self._pending.values()):
            await pending.client.disconnect()
        self._pending.clear()

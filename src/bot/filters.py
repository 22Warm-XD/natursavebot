from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from src.config import Settings


class OwnerFilter(BaseFilter):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return bool(user and user.id == self.settings.owner_telegram_id)

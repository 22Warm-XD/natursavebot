from __future__ import annotations

import logging
from datetime import UTC, datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo

from src.config import Settings
from src.db.repositories.reminders import open_reminders
from src.db.repositories.settings import get_all_settings, set_setting
from src.db.session import get_session
from src.services.digest import build_digest
from src.services.llm.router import LLMRouter
from src.utils.text import html_quote


logger = logging.getLogger(__name__)


class ReminderScheduler:
    def __init__(self, bot: Bot, settings: Settings, llm: LLMRouter) -> None:
        self.bot = bot
        self.settings = settings
        self.llm = llm
        self.scheduler = AsyncIOScheduler(timezone=settings.timezone)

    def start(self) -> None:
        self.scheduler.add_job(self.tick, "interval", seconds=60, id="reminders_tick", replace_existing=True)
        self.scheduler.start()

    async def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)

    async def tick(self) -> None:
        async with get_session() as session:
            now = datetime.now(UTC).replace(tzinfo=None)
            reminders = await open_reminders(session, limit=200)
            for reminder in reminders:
                if reminder.remind_at <= now:
                    try:
                        await self.bot.send_message(
                            self.settings.owner_telegram_id,
                            f"<b>Напоминание</b>\n{html_quote(reminder.text)}",
                        )
                        reminder.status = "done"
                        reminder.last_ping_at = now
                    except Exception:
                        logger.exception("failed to send reminder %s", reminder.id)
                elif reminder.last_ping_at is None:
                    minutes_left = int((reminder.remind_at - now).total_seconds() // 60)
                    if any(0 <= minutes_left <= lead for lead in self.settings.reminder_lead_minutes):
                        try:
                            await self.bot.send_message(
                                self.settings.owner_telegram_id,
                                f"<b>Скоро напоминание</b>\nЧерез ~{minutes_left} мин.\n{html_quote(reminder.text)}",
                            )
                            reminder.last_ping_at = now
                        except Exception:
                            logger.exception("failed to send reminder lead %s", reminder.id)
            await self._maybe_send_digest(session)
            await session.commit()

    async def _maybe_send_digest(self, session) -> None:
        values = await get_all_settings(session)
        if not values.get("digest_enabled", False):
            return
        now_local = datetime.now(ZoneInfo(str(values.get("timezone") or self.settings.timezone)))
        digest_time = str(values.get("digest_time") or self.settings.digest_time)
        if now_local.strftime("%H:%M") != digest_time:
            return
        today = now_local.date().isoformat()
        if values.get("digest_last_sent_date") == today:
            return
        digest = await build_digest(session, self.llm)
        await self.bot.send_message(self.settings.owner_telegram_id, f"<b>Дайджест</b>\n{digest}")
        await set_setting(session, "digest_last_sent_date", today)

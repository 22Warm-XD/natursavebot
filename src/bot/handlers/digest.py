from __future__ import annotations

import re

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.db.repositories.settings import set_setting
from src.db.session import get_session
from src.services.digest import build_digest
from src.services.llm.router import LLMRouter


router = Router(name="digest")


@router.message(Command("digest"))
async def cmd_digest(message: Message, llm: LLMRouter) -> None:
    arg = (message.text or "").split(maxsplit=1)
    value = arg[1].strip() if len(arg) > 1 else "now"
    async with get_session() as session:
        if value == "now":
            digest = await build_digest(session, llm)
            await message.answer(digest)
            return
        if value in {"on", "off"}:
            await set_setting(session, "digest_enabled", value == "on")
            await session.commit()
            await message.answer(f"Digest: {value}.")
            return
        match = re.match(r"at\s+([0-2]\d:[0-5]\d)$", value)
        if match:
            await set_setting(session, "digest_time", match.group(1))
            await set_setting(session, "digest_enabled", True)
            await session.commit()
            await message.answer(f"Digest включён на {match.group(1)}.")
            return
    await message.answer("Использование: /digest now, /digest on, /digest off, /digest at HH:MM")

from __future__ import annotations

import os
import tempfile

from aiogram import F, Router
from aiogram.types import Message

from src.bot.handlers.send import create_and_show_draft
from src.bot.handlers.status import build_business_status, build_health_status
from src.config import Settings
from src.db.repositories.chats import find_chats
from src.db.repositories.messages import recent_messages, search_messages
from src.db.repositories.reminders import create_reminder
from src.db.repositories.settings import set_setting
from src.db.repositories.todos import create_todo
from src.db.session import get_session
from src.services.agent import AgentRouter
from src.services.digest import build_digest
from src.services.llm.router import LLMRouter
from src.services.search import format_search_result
from src.services.summarizer import summarize_chat
from src.services.task_extractor import extract_tasks_heuristic
from src.userbot.client import UserbotManager
from src.utils.text import clean_text
from src.utils.timeparse import parse_reminder_phrase


router = Router(name="free_text")


@router.message(F.voice)
async def voice_message(message: Message, llm: LLMRouter, agent: AgentRouter, settings: Settings, userbot: UserbotManager) -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    path = tmp.name
    tmp.close()
    try:
        await message.bot.download(message.voice.file_id, destination=path)
        text = await llm.transcribe(path)
    except Exception as exc:
        await message.answer(f"Не удалось разобрать голосовое: {exc}")
        return
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    await message.answer(f"<b>Транскрипция</b>\n{text}")
    await _route_text(message, text, agent=agent, llm=llm, settings=settings, userbot=userbot)


@router.message(F.text & ~F.text.startswith("/"))
async def free_text(message: Message, agent: AgentRouter, llm: LLMRouter, settings: Settings, userbot: UserbotManager) -> None:
    await _route_text(message, message.text or "", agent=agent, llm=llm, settings=settings, userbot=userbot)


async def _route_text(message: Message, text: str, *, agent: AgentRouter, llm: LLMRouter, settings: Settings, userbot: UserbotManager) -> None:
    lowered = text.lower().strip()
    if lowered in {"статус", "business status", "бизнес статус"}:
        await message.answer(await build_business_status(settings, userbot))
        return
    if lowered in {"проверка", "health"}:
        await message.answer(await build_health_status(settings, userbot))
        return

    intent = await agent.route(text)
    name = intent.get("intent", "unknown")

    if name == "send_message":
        recipient = str(intent.get("recipient") or "").strip()
        body = str(intent.get("text") or "").strip()
        if not recipient or not body:
            await message.answer("Не понял, кому и что отправить. Пример: Ответь Олегу: созвон в 8.")
            return
        async with get_session() as session:
            chats = await find_chats(session, recipient, limit=1)
            if not chats:
                await message.answer("Чат не найден. В Business mode он появится после первого сообщения, доступного боту.")
                return
            await create_and_show_draft(message, session, chat_id=chats[0].chat_id, recipient_label=chats[0].title or recipient, text=body)
            await session.commit()
        return

    if name == "create_reminder":
        parsed = parse_reminder_phrase(str(intent.get("text") or text), tz_name=settings.timezone)
        if not parsed:
            await message.answer("Похоже на напоминание, но я не понял дату. Пример: завтра в 18:00 позвонить клиенту.")
            return
        async with get_session() as session:
            reminder = await create_reminder(session, text_value=parsed.text, remind_at=parsed.when)
            await session.commit()
        await message.answer(f"Напоминание #{reminder.id}: <code>{parsed.when.isoformat(sep=' ', timespec='minutes')} UTC</code>\n{parsed.text}")
        return

    if name == "search_messages":
        query = str(intent.get("query") or text)
        async with get_session() as session:
            rows = await search_messages(session, query, limit=10)
        await message.answer("\n\n".join(format_search_result(row) for row in rows) if rows else "В локальной базе ничего не найдено.")
        return

    if name in {"summarize_chat", "catchup_chat"}:
        query = str(intent.get("chat") or intent.get("contact") or clean_text(text))
        async with get_session() as session:
            chats = await find_chats(session, query, limit=1)
            if not chats:
                await message.answer("Не нашёл чат для выжимки. Уточни имя или username.")
                return
            summary = await summarize_chat(session, llm, chats[0].chat_id, kind="catchup" if name == "catchup_chat" else "summary")
            await session.commit()
        await message.answer(summary)
        return

    if name == "extract_tasks":
        query = str(intent.get("chat") or intent.get("contact") or "")
        async with get_session() as session:
            chats = await find_chats(session, query, limit=1) if query else []
            messages = await recent_messages(session, chats[0].chat_id, limit=80) if chats else []
            tasks = extract_tasks_heuristic([msg.text or msg.caption or "" for msg in messages] if messages else [text], tz_name=settings.timezone)
            for task in tasks:
                await create_todo(
                    session,
                    title=task.title,
                    actor=task.actor,
                    deadline_at=task.deadline_at,
                    chat_id=chats[0].chat_id if chats else None,
                    source_text=task.source_text,
                )
            await session.commit()
        await message.answer(f"Найдено задач: {len(tasks)}.")
        return

    if name == "digest":
        async with get_session() as session:
            digest = await build_digest(session, llm)
        await message.answer(digest)
        return

    if name == "settings_change":
        provider = "anthropic" if "anthropic" in lowered or "claude" in lowered else ("gemini" if "gemini" in lowered else ("openai" if "openai" in lowered else None))
        if provider:
            async with get_session() as session:
                await set_setting(session, "llm_provider", provider)
                await session.commit()
            llm.settings.llm_provider = provider
            await message.answer(f"LLM provider: {provider}.")
            return

    await message.answer("Не понял запрос. Нажми /help или напиши конкретнее.")

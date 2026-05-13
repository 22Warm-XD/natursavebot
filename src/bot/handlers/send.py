from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import send_confirm_keyboard
from src.bot.states import DraftStates
from src.business_bot.connection import latest_business_connection
from src.business_bot.sender import send_business_draft
from src.config import Settings
from src.db.repositories.chats import find_chats
from src.db.repositories.messages import create_draft, get_draft
from src.db.session import get_session
from src.userbot.client import UserbotManager
from src.utils.text import html_quote


router = Router(name="send")


@router.message(Command("send", "reply"))
async def cmd_send(message: Message) -> None:
    payload = (message.text or "").split(maxsplit=1)
    if len(payload) < 2 or "|" not in payload[1]:
        await message.answer("Формат: /reply Клиент | текст ответа")
        return
    recipient, text = [part.strip() for part in payload[1].split("|", 1)]
    if not recipient or not text:
        await message.answer("Нужны получатель и текст: /reply Клиент | текст ответа")
        return
    async with get_session() as session:
        chats = await find_chats(session, recipient, limit=1)
        if not chats and recipient.lstrip("-").isdigit():
            from src.db.repositories.chats import get_chat_by_id

            chat = await get_chat_by_id(session, int(recipient))
            chats = [chat] if chat else []
        if not chats:
            await message.answer("Чат не найден. В Business mode чат появится после первого сообщения, доступного боту.")
            return
        await create_and_show_draft(
            message,
            session,
            chat_id=chats[0].chat_id,
            recipient_label=chats[0].title or recipient,
            text=text,
        )
        await session.commit()


async def create_and_show_draft(message: Message, session, *, chat_id: int, recipient_label: str, text: str) -> None:
    connection = await latest_business_connection(session)
    draft = await create_draft(
        session,
        chat_id=chat_id,
        recipient_label=recipient_label,
        text_value=text,
        business_connection_id=connection.connection_id if connection else None,
    )
    await message.answer(
        "<b>Черновик ответа</b>\n"
        f"Кому: <code>{html_quote(recipient_label)}</code>\n"
        f"Chat ID: <code>{chat_id}</code>\n\n"
        f"{html_quote(text)}\n\n"
        "Сообщение уйдёт только после подтверждения.",
        reply_markup=send_confirm_keyboard(draft.id),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("send:"))
async def send_callback(callback: CallbackQuery, userbot: UserbotManager, state: FSMContext, settings: Settings) -> None:
    _, action, draft_id = callback.data.split(":", 2)
    if action not in {"confirm", "edit", "cancel"}:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return
    async with get_session() as session:
        draft = await get_draft(session, draft_id)
        if draft is None:
            await callback.answer("Черновик не найден.", show_alert=True)
            return
        if draft.status != "pending":
            await callback.answer("Черновик уже обработан.", show_alert=True)
            if isinstance(callback.message, Message):
                await callback.message.edit_reply_markup(reply_markup=None)
            return
        if action == "cancel":
            draft.status = "cancelled"
            await session.commit()
            if isinstance(callback.message, Message):
                await callback.message.edit_text("Черновик отменён.")
            await callback.answer()
            return
        if action == "edit":
            await state.set_state(DraftStates.editing)
            await state.update_data(draft_id=draft_id)
            if isinstance(callback.message, Message):
                await callback.message.answer("Пришли новый текст для черновика.")
            await callback.answer()
            return
        if settings.telegram_mode in {"business", "both"}:
            try:
                await send_business_draft(callback.bot, session, draft, settings)
            except RuntimeError as exc:
                await callback.answer(str(exc), show_alert=True)
                return
        else:
            client = userbot.get_client()
            if client is None:
                await callback.answer("Legacy userbot не подключён.", show_alert=True)
                return
            await client.send_message(draft.chat_id, draft.text)
        draft.status = "sent"
        await session.commit()
    if isinstance(callback.message, Message):
        await callback.message.edit_text("Сообщение отправлено.")
    await callback.answer()


@router.message(DraftStates.editing)
async def edit_draft_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    draft_id = data.get("draft_id")
    text = message.text or ""
    async with get_session() as session:
        draft = await get_draft(session, draft_id)
        if draft is None:
            await message.answer("Черновик не найден.")
            await state.clear()
            return
        draft.text = text
        draft.status = "pending"
        await session.commit()
    await state.clear()
    await message.answer(
        "<b>Обновлённый черновик</b>\n"
        f"Кому: <code>{html_quote(draft.recipient_label)}</code>\n\n{html_quote(text)}",
        reply_markup=send_confirm_keyboard(draft.id),
    )

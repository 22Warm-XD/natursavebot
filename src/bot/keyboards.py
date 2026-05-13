from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def send_confirm_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data=f"send:confirm:{draft_id}"),
                InlineKeyboardButton(text="✏️ Изменить", callback_data=f"send:edit:{draft_id}"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"send:cancel:{draft_id}")],
        ]
    )


def todo_keyboard(todo_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Done", callback_data=f"todo:done:{todo_id}"),
                InlineKeyboardButton(text="Cancel", callback_data=f"todo:cancel:{todo_id}"),
                InlineKeyboardButton(text="Later", callback_data=f"todo:later:{todo_id}"),
            ]
        ]
    )


def settings_keyboard(provider: str, save_mode: bool, autoreply: bool, digest: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"LLM: {provider}", callback_data="settings:provider"),
                InlineKeyboardButton(text=f"Save: {'on' if save_mode else 'off'}", callback_data="settings:toggle_save"),
            ],
            [
                InlineKeyboardButton(text=f"Auto: {'on' if autoreply else 'off'}", callback_data="settings:toggle_auto"),
                InlineKeyboardButton(text=f"Digest: {'on' if digest else 'off'}", callback_data="settings:toggle_digest"),
            ],
        ]
    )

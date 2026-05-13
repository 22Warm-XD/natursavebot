from __future__ import annotations

from aiogram.types import Update


def business_update_kind(update: Update) -> str | None:
    if update.business_connection:
        return "business_connection"
    if update.business_message:
        return "business_message"
    if update.edited_business_message:
        return "edited_business_message"
    if update.deleted_business_messages:
        return "deleted_business_messages"
    return None

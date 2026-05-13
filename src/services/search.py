from __future__ import annotations

from src.db.models import Message
from src.utils.text import clip


def format_search_result(message: Message) -> str:
    sender = message.sender_name or ("me" if message.direction == "outgoing" else "unknown")
    chat = message.chat_title or str(message.chat_id)
    text = clip(message.text, 180)
    return f"{chat} · {sender}: {text}"

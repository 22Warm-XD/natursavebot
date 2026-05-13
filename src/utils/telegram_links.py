from __future__ import annotations


def message_ref(chat_id: int | None, message_id: int | None) -> str:
    if not chat_id or not message_id:
        return ""
    normalized = str(chat_id)
    if normalized.startswith("-100"):
        return f"https://t.me/c/{normalized[4:]}/{message_id}"
    return f"chat_id={chat_id}, message_id={message_id}"

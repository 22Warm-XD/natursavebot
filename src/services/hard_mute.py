from __future__ import annotations

import asyncio
from dataclasses import dataclass

from telethon.errors import FloodWaitError

from src.config import Settings


@dataclass(slots=True)
class HardMuteDeleteResult:
    delete_for_everyone_success: bool = False
    delete_local_success: bool = False
    delete_error: str | None = None


class DotCommandCooldown:
    def __init__(self) -> None:
        self._last: dict[tuple[int, str], float] = {}

    def check(self, owner_id: int, command: str, now: float, cooldown_seconds: int) -> float:
        key = (owner_id, command)
        last = self._last.get(key, 0)
        left = cooldown_seconds - (now - last)
        if left > 0:
            return left
        self._last[key] = now
        return 0


async def delete_hard_muted_message(
    client,
    *,
    chat_id: int,
    message_id: int,
    delete_for_everyone: bool = True,
) -> HardMuteDeleteResult:
    result = HardMuteDeleteResult()
    errors: list[str] = []
    if delete_for_everyone:
        try:
            await client.delete_messages(chat_id, [message_id], revoke=True)
            result.delete_for_everyone_success = True
            result.delete_local_success = True
            return result
        except FloodWaitError as exc:
            await asyncio.sleep(exc.seconds)
            errors.append(f"FloodWait {exc.seconds}s")
        except Exception as exc:
            errors.append(_short_error(exc))

    try:
        await client.delete_messages(chat_id, [message_id], revoke=False)
        result.delete_local_success = True
    except FloodWaitError as exc:
        await asyncio.sleep(exc.seconds)
        errors.append(f"local FloodWait {exc.seconds}s")
    except Exception as exc:
        errors.append(f"local {_short_error(exc)}")

    result.delete_error = "; ".join(errors)[:500] if errors else None
    return result


def clamp_repeat_count(requested: int, settings: Settings) -> tuple[int, bool]:
    max_count = min(max(int(settings.max_repeat_count), 1), 10)
    value = max(int(requested), 1)
    return min(value, max_count), value > max_count


def parse_repeat_args(value: str | None) -> tuple[int | None, str | None]:
    text = (value or "").strip()
    if not text:
        return None, None
    first, _, rest = text.partition(" ")
    if not first.isdigit() or not rest.strip():
        return None, None
    return int(first), rest.strip()


def dot_usage(command: str) -> str:
    if command in {".spam", ".repeat"}:
        return "Usage: .repeat 5 привет"
    if command == ".type":
        return "Usage: .type текст"
    return "Доступно только в userbot/Telethon mode."


def _short_error(exc: Exception) -> str:
    text = str(exc) or type(exc).__name__
    return text.replace("\n", " ")[:240]

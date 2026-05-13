from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from src.utils.timeparse import parse_reminder_phrase
from src.utils.text import clean_text


TASK_RE = re.compile(
    r"(?:надо|нужно|нужна|обещал(?:а)?|сделаю|сделать|должен|должна|не забыть)\s+(.+)",
    re.I,
)


@dataclass(slots=True)
class ExtractedTask:
    title: str
    actor: str | None = None
    deadline_at: datetime | None = None
    source_text: str | None = None


def extract_tasks_heuristic(messages: list[str], *, tz_name: str = "Asia/Yekaterinburg") -> list[ExtractedTask]:
    tasks: list[ExtractedTask] = []
    now = datetime.now(timezone.utc)
    for raw in messages:
        text = clean_text(raw)
        if not text:
            continue
        match = TASK_RE.search(text)
        if not match:
            continue
        title = match.group(1).strip(" .,:;")
        parsed = parse_reminder_phrase(text, tz_name=tz_name, now=now)
        deadline = parsed.when if parsed else None
        actor = "я" if re.search(r"\b(я|мне|сделаю|обещал)\b", text, re.I) else None
        tasks.append(ExtractedTask(title=title, actor=actor, deadline_at=deadline, source_text=text))
    return tasks

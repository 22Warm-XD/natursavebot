from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


TIME_RE = re.compile(r"\b(?:в\s*)?([01]?\d|2[0-3])[:.]([0-5]\d)\b", re.I)
DATE_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b")
RELATIVE_RE = re.compile(
    r"через\s+(\d+)\s*(минуты|минут|мин|часов|часа|час|дней|дня|день)",
    re.I,
)


@dataclass(slots=True)
class ParsedReminder:
    text: str
    when: datetime


def now_in_tz(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def parse_reminder_phrase(text: str, *, tz_name: str, now: datetime | None = None) -> ParsedReminder | None:
    source = " ".join(text.strip().split())
    if not source:
        return None

    tz = ZoneInfo(tz_name)
    local_now = now.astimezone(tz) if now and now.tzinfo else (now.replace(tzinfo=tz) if now else datetime.now(tz))
    lowered = source.lower()

    target: datetime | None = None

    rel = RELATIVE_RE.search(lowered)
    if rel:
        amount = int(rel.group(1))
        unit = rel.group(2)
        if unit.startswith("мин"):
            target = local_now + timedelta(minutes=amount)
        elif unit.startswith("час"):
            target = local_now + timedelta(hours=amount)
        else:
            target = local_now + timedelta(days=amount)

    if target is None:
        base = local_now
        if "послезавтра" in lowered:
            base = local_now + timedelta(days=2)
        elif "завтра" in lowered:
            base = local_now + timedelta(days=1)
        elif "сегодня" in lowered:
            base = local_now

        date_match = DATE_RE.search(lowered)
        if date_match:
            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year_raw = date_match.group(3)
            year = int(year_raw) if year_raw else local_now.year
            if year < 100:
                year += 2000
            base = base.replace(year=year, month=month, day=day)

        time_match = TIME_RE.search(lowered)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            target = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= local_now and not any(marker in lowered for marker in ("сегодня", "завтра", "послезавтра")) and not date_match:
                target += timedelta(days=1)

    if target is None:
        return None

    cleaned = source
    cleaned = re.sub(r"^(поставь\s+)?(напоминание|напомни)(\s+мне)?", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"\b(сегодня|завтра|послезавтра)\b", "", cleaned, flags=re.I)
    cleaned = TIME_RE.sub("", cleaned)
    cleaned = DATE_RE.sub("", cleaned)
    cleaned = RELATIVE_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-:")
    if not cleaned:
        cleaned = source

    return ParsedReminder(text=cleaned, when=to_utc_naive(target))

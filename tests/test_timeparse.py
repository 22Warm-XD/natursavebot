from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.utils.timeparse import parse_reminder_phrase


def test_parse_tomorrow_at_time_to_utc_naive() -> None:
    now = datetime(2026, 5, 12, 12, 0, tzinfo=ZoneInfo("Asia/Yekaterinburg"))

    parsed = parse_reminder_phrase("поставь напоминание завтра в 18:00 позвонить", tz_name="Asia/Yekaterinburg", now=now)

    assert parsed is not None
    assert parsed.text == "позвонить"
    assert parsed.when == datetime(2026, 5, 13, 13, 0)


def test_parse_relative_hours() -> None:
    now = datetime(2026, 5, 12, 12, 0, tzinfo=ZoneInfo("Asia/Yekaterinburg"))

    parsed = parse_reminder_phrase("напомни через 2 часа проверить билд", tz_name="Asia/Yekaterinburg", now=now)

    assert parsed is not None
    assert parsed.text == "проверить билд"
    assert parsed.when == datetime(2026, 5, 12, 9, 0)

from __future__ import annotations

from src.config import Settings


def test_reminder_lead_minutes_accepts_json_array(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("REMINDER_LEAD_MINUTES=[15,60,240,1440]\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.reminder_lead_minutes == [15, 60, 240, 1440]

from __future__ import annotations

from types import SimpleNamespace

from src.services.user_info import format_user_info


def test_info_reply_text_contains_user_fields_and_no_registration_guess() -> None:
    user = SimpleNamespace(
        id=123456789,
        username="username",
        first_name="Иван",
        last_name="Иванов",
        bot=False,
        premium=True,
        verified=False,
        scam=False,
        fake=False,
        restricted=False,
        lang_code="ru",
        mutual_contact=None,
        phone=None,
        access_hash=123456789999,
        status=None,
    )

    text = format_user_info(user, chat_id=500, message_id=42, common_chats_count=2, profile_photo_count=1)

    assert "ID: <code>123456789</code>" in text
    assert "Username: <code>@username</code>" in text
    assert "Имя: <code>Иван</code>" in text
    assert "Дата регистрации: недоступна через Telegram API" in text
    assert "202" not in text.split("Дата регистрации:", 1)[1]

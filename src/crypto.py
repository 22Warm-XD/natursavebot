from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from src.config import get_settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is required before storing secrets")
    return Fernet(key.encode())


def encrypt_secret(value: str | None) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Cannot decrypt secret with current ENCRYPTION_KEY") from exc

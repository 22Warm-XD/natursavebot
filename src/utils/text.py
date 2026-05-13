from __future__ import annotations

import html
import re
from textwrap import shorten


_TOKEN_RE = re.compile(r"[\wа-яА-ЯёЁ@.+-]+", re.U)


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clip(value: str | None, limit: int = 900) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    return shorten(text, width=limit, placeholder="...")


def html_quote(value: str | None) -> str:
    return html.escape(value or "", quote=False)


def make_fts_query(value: str) -> str:
    tokens = _TOKEN_RE.findall(value.lower())
    return " ".join(f'"{token}"' for token in tokens[:12])


def chunk_text(items: list[str], max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for item in items:
        item = item.strip()
        if not item:
            continue
        if len(current) + len(item) + 1 > max_chars and current:
            chunks.append(current)
            current = item
        else:
            current = item if not current else current + "\n" + item
    if current:
        chunks.append(current)
    return chunks


def parse_boolish(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in {"on", "yes", "true", "1", "да", "вкл", "включить"}:
        return True
    if lowered in {"off", "no", "false", "0", "нет", "выкл", "выключить"}:
        return False
    return None

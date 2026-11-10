"""Shared helpers."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote


def slugify(value: str, max_len: int = 80) -> str:
    if not value:
        return "unnamed"
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return (value[:max_len].strip("_") or "unnamed")


def iri_safe(value: str) -> str:
    return quote(value, safe=":/#[]@!$&'()*+,;=-._~")


def split_normal_date(normal: str | None) -> tuple[str | None, str | None]:
    if not normal:
        return None, None
    normal = normal.strip()
    if "/" in normal:
        a, b = normal.split("/", 1)
        return a or None, b or None
    return normal, normal

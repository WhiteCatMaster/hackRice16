"""Nessie stores dates at day precision. We need minutes.

Velocity ("five charges in twenty minutes") and impossible travel ("Omaha then
Miami 95 minutes later") are meaningless without a time of day, so we smuggle ours
through the one free-text field Nessie round-trips faithfully: `description`.

    "Hy-Vee"  ->  "Hy-Vee [t=18:41]"

`decode` puts it back and hands the clean description to the UI, so the tag never
reaches a judge's screen.
"""
from __future__ import annotations

import re

TAG = re.compile(r"\s*\[t=(\d{2}):(\d{2})\]\s*$")


def encode(description: str | None, occurred_at: str | None) -> str:
    text = (description or "").strip()
    if not occurred_at or "T" not in occurred_at:
        return text
    return f"{text} [t={occurred_at[11:16]}]".strip()


def decode(description: str | None, fallback_date: str | None) -> tuple[str, str | None]:
    """-> (clean description, ISO timestamp or None)"""
    text = description or ""
    match = TAG.search(text)
    if not match:
        return text.strip(), None
    clean = TAG.sub("", text).strip()
    if not fallback_date:
        return clean, None
    return clean, f"{fallback_date[:10]}T{match.group(1)}:{match.group(2)}"

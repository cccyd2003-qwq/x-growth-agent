"""Small shared helpers."""

from __future__ import annotations

import json
import re
from typing import Any, Optional


def strip_code_fences(text: str) -> str:
    text = text.strip()
    # ```json ... ```  or  ``` ... ```
    m = re.match(r"^```(?:json|JSON)?\s*(.*?)\s*```$", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def extract_json(text: str) -> Optional[Any]:
    """Best-effort extraction of a JSON object/array from a model's text output.

    Handles raw JSON, fenced JSON, and JSON embedded in surrounding prose.
    Returns the parsed value, or None if nothing parseable was found.
    """
    if not text:
        return None
    candidate = strip_code_fences(text)

    # Try a direct parse first.
    try:
        return json.loads(candidate)
    except Exception:
        pass

    # Fall back to the first balanced {...} or [...] span.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = candidate.find(opener)
        if start == -1:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(candidate)):
            ch = candidate[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    span = candidate[start : i + 1]
                    try:
                        return json.loads(span)
                    except Exception:
                        break
    return None


def truncate(text: str, n: int = 280) -> str:
    text = text.strip()
    return text if len(text) <= n else text[: n - 1] + "…"


from datetime import datetime, timezone  # noqa: E402


def parse_tweet_time(s: str):
    """Parse a tweet timestamp. Handles Twitter legacy and ISO 8601 formats."""
    if not s:
        return None
    s = s.strip()
    try:
        # Twitter legacy: "Sun Jun 21 10:46:28 +0000 2026"
        return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
    except Exception:
        pass
    try:
        # ISO: "2026-06-21T10:46:28.000Z"
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def human_age(created_at: str, now: "datetime | None" = None, lang: str = "en") -> str:
    """Localized 'time ago' string from a tweet timestamp, computed at call time."""
    from .i18n import t

    dt = parse_tweet_time(created_at)
    if not dt:
        return ""
    now = now or datetime.now(timezone.utc)
    secs = max(0, (now - dt).total_seconds())
    minutes = int(secs // 60)
    if minutes < 1:
        return t(lang, "just_now")
    if minutes < 60:
        return t(lang, "minutes_ago", n=minutes)
    hours = minutes // 60
    if hours < 24:
        return t(lang, "hours_ago", n=hours)
    days = hours // 24
    return t(lang, "days_ago", n=days)

"""Bark notifier — minimal iOS push.

Stub: Bark is a tiny iOS push service. We send the first candidate as the body
and link back to the tweet. No buttons (Bark doesn't support them); it's the
lightweight "just buzz my phone" option.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

import httpx

from ..models import Candidate, Post
from .base import Notifier, NotifierError


class BarkNotifier(Notifier):
    name = "bark"

    def __init__(self, server: str = "https://api.day.app", device_key: str = "", timeout: float = 20.0):
        self.server = (server or "https://api.day.app").rstrip("/")
        self.device_key = device_key or ""
        self._timeout = timeout

    def configured(self) -> bool:
        return bool(self.device_key)

    def _push(self, title: str, body: str, url: str = "") -> None:
        if not self.device_key:
            raise NotifierError("missing bark device_key")
        endpoint = f"{self.server}/{self.device_key}/{quote(title)}/{quote(body)}"
        params = {"url": url} if url else {}
        resp = httpx.get(endpoint, params=params, timeout=self._timeout)
        data = resp.json()
        if data.get("code") not in (200, None):
            raise NotifierError(f"bark push failed: {data}")

    def send(self, post: Post, candidates: list[Candidate]) -> Optional[str]:
        first = candidates[0].text if candidates else "(no draft)"
        self._push(f"@{post.username} 新帖", first, post.url)
        return None

    def send_text(self, text: str) -> Optional[str]:
        self._push("xgrowth", text)
        return None

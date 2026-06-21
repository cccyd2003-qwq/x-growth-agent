"""飞书 (Lark) notifier — custom-bot webhook.

Stub / minimal implementation: posts an interactive-ish text card to a Lark
custom bot webhook. Buttons (换一批) are not wired here yet; that needs the Lark
event subscription flow. Good enough for "ping me when there's a new draft".
"""

from __future__ import annotations

from typing import Optional

import httpx

from ..models import Candidate, Post
from .base import Notifier, NotifierError


class LarkNotifier(Notifier):
    name = "lark"

    def __init__(self, webhook_url: str, timeout: float = 20.0):
        self.webhook_url = webhook_url or ""
        self._timeout = timeout

    def configured(self) -> bool:
        return bool(self.webhook_url)

    def _post(self, payload: dict) -> dict:
        if not self.webhook_url:
            raise NotifierError("missing lark webhook_url")
        resp = httpx.post(self.webhook_url, json=payload, timeout=self._timeout)
        data = resp.json()
        if data.get("code") not in (0, None):
            raise NotifierError(f"lark webhook failed: {data}")
        return data

    def _text(self, post: Post, candidates: list[Candidate]) -> str:
        lines = [f"🐦 @{post.username}", post.text, "—————"]
        for i, c in enumerate(candidates, 1):
            lines.append(f"{i}. [{c.style}] {c.text}")
        lines.append(f"原帖: {post.url}")
        return "\n".join(lines)

    def send(self, post: Post, candidates: list[Candidate]) -> Optional[str]:
        self._post({"msg_type": "text", "content": {"text": self._text(post, candidates)}})
        return None

    def send_text(self, text: str) -> Optional[str]:
        self._post({"msg_type": "text", "content": {"text": text}})
        return None

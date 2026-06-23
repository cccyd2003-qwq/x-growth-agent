"""Notifier interface."""

from __future__ import annotations

from typing import Optional

from ..models import Candidate, Post


class NotifierError(RuntimeError):
    pass


class Notifier:
    name = "base"

    def send(self, post: Post, candidates: list[Candidate]) -> Optional[str]:
        """Push a post + its candidate replies. Returns a message id if any."""
        raise NotImplementedError

    def send_text(self, text: str) -> Optional[str]:
        """Plain-text message, used by `xgrowth test-notify`."""
        raise NotImplementedError

    def send_digest(self, items: list[dict]) -> Optional[str]:
        """Push a whole poll cycle at once. Default: fall back to one send per post.

        items: [{"post": Post, "candidates": [Candidate, ...]}, ...]
        Telegram overrides this with a single index message + drill-in buttons.
        """
        last = None
        for it in items:
            last = self.send(it["post"], it["candidates"])
        return last

    def deliver(self, items: list[dict]) -> list[dict]:
        """Deliver a poll cycle. Returns mappings (tweet_id/thread_id/message_id)
        the orchestrator should persist. Default: a digest, no mappings.
        Telegram overrides this to support forum-Topic-per-post mode.
        """
        self.send_digest(items)
        return []

    def configured(self) -> bool:
        return True

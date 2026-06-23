"""Ties the pieces together: post -> engine -> store -> notifier."""

from __future__ import annotations

import logging
from typing import Optional

from .engines.base import Engine
from .models import Candidate, Post
from .notifiers.base import Notifier
from .store import Store

log = logging.getLogger("xgrowth.orchestrator")


class Orchestrator:
    def __init__(self, cfg: dict, store: Store, engine: Engine, notifier: Notifier):
        self.cfg = cfg
        self.store = store
        self.engine = engine
        self.notifier = notifier

    @property
    def _styles(self) -> list[str]:
        return list(self.cfg.get("engine", {}).get("styles", []) or [])

    @property
    def _num(self) -> int:
        return int(self.cfg.get("engine", {}).get("num_candidates", 3))

    def draft(self, post: Post, instruction: Optional[str] = None) -> list[Candidate]:
        return self.engine.generate(post, self._styles, self._num, instruction=instruction)

    def handle_post(self, post: Post, notify: bool = True) -> list[Candidate]:
        """Draft replies for a single post, persist, and (optionally) notify directly.

        Used by `xgrowth draft`. The poll loop uses `handle_cycle` for digests.
        """
        log.info("drafting replies for @%s tweet %s", post.username, post.tweet_id)
        candidates = self.draft(post)
        self.store.save_candidates(post, candidates)
        if notify and self.notifier.configured():
            try:
                msg_id = self.notifier.send(post, candidates)
                self.store.mark_notified(post.tweet_id, msg_id or "")
            except Exception as e:  # don't let a notify failure lose the draft
                log.error("notify failed for %s: %s", post.tweet_id, e)
        return candidates

    def handle_cycle(self, posts: list[Post], notify: bool = True) -> list[dict]:
        """Draft replies for every new post in a poll cycle, then send ONE digest.

        Returns the list of {post, candidates} items handled.
        """
        items: list[dict] = []
        for post in posts:
            try:
                log.info("drafting @%s tweet %s", post.username, post.tweet_id)
                candidates = self.draft(post)
                self.store.save_candidates(post, candidates)
                items.append({"post": post, "candidates": candidates})
            except Exception as e:
                log.error("draft failed for %s: %s", post.tweet_id, e)
        if items and notify and self.notifier.configured():
            try:
                mappings = self.notifier.deliver(items) or []
                for m in mappings:
                    tid = m.get("tweet_id")
                    if not tid:
                        continue
                    if m.get("thread_id") is not None:
                        self.store.map_topic(str(m["thread_id"]), tid)
                    if m.get("message_id"):
                        self.store.map_message(str(m["message_id"]), tid)
            except Exception as e:
                log.error("notify failed: %s", e)
        return items

    def regenerate(
        self, tweet_id: str, instruction: Optional[str] = None
    ) -> Optional[tuple[Post, list[Candidate]]]:
        """Re-draft an existing post (🔄 button, or a free-text steer from the user)."""
        row = self.store.get_candidate_row(tweet_id)
        if not row:
            return None
        post: Post = row["post"]
        candidates = self.draft(post, instruction=instruction)
        self.store.update_candidates(tweet_id, candidates)
        return post, candidates

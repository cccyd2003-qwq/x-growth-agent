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
        """Handle a poll cycle.

        forum mode (lazy): stage the posts (NO drafting), send one index message
        with a button per post. Drafting + topic creation happen only when the
        user taps a post (see open_post). Saves cost and avoids topic floods.

        dm mode: draft every post now and send one digest.
        """
        is_forum = getattr(self.notifier, "mode", "dm") == "forum"
        if is_forum and hasattr(self.notifier, "send_index"):
            for post in posts:
                self.store.save_candidates(post, [])  # stage post, no candidates yet
            if notify and self.notifier.configured():
                try:
                    self.notifier.send_index(posts)
                except Exception as e:
                    log.error("index notify failed: %s", e)
            return [{"post": p, "candidates": []} for p in posts]

        # dm mode: draft everything now
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
                self.notifier.deliver(items)
            except Exception as e:
                log.error("notify failed: %s", e)
        return items

    def open_post(self, tweet_id: str):
        """Lazy: draft replies for a staged post the first time it's opened.

        Returns (post, candidates) or None. Reuses existing candidates if already drafted.
        """
        row = self.store.get_candidate_row(tweet_id)
        if not row:
            return None
        post: Post = row["post"]
        candidates = row["candidates"]
        if not candidates:
            log.info("drafting (on open) @%s tweet %s", post.username, post.tweet_id)
            candidates = self.draft(post)
            self.store.update_candidates(tweet_id, candidates)
        return post, candidates

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

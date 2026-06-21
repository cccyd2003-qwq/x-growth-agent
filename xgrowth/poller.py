"""The always-awake scheduler: poll the watchlist on a time window, draft, and
push ONE digest per cycle. Also hosts the Telegram listener that powers drill-in
(open a post), 🔄 换一批, and conversational regeneration (text the bot to revise).
"""

from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from .orchestrator import Orchestrator
from .store import Store
from .twitter import RateLimited, TwitterError

log = logging.getLogger("xgrowth.poller")


def run_once(cfg: dict, store: Store, twitter, orch: Orchestrator) -> int:
    """One poll cycle: detect new posts across the watchlist, draft, send a digest.

    Uses the provider's batched `latest_for` (one call per 100 accounts).
    """
    poll = cfg.get("poll", {})
    entries = store.list_watch(only_enabled=True)
    if not entries:
        return 0
    by_id = {e.user_id: e for e in entries}

    try:
        latest = twitter.latest_for(
            list(by_id.keys()),
            exclude_replies=bool(poll.get("exclude_replies", True)),
            exclude_retweets=bool(poll.get("exclude_retweets", True)),
        )
    except RateLimited:
        log.warning("rate limited; backing off this cycle")
        return 0
    except TwitterError as e:
        log.error("twitter error: %s", e)
        return 0

    new_posts = []
    for uid, post in latest.items():
        entry = by_id.get(uid)
        if not entry:
            continue
        post.username = entry.username
        if post.tweet_id == entry.last_seen_tweet_id:
            continue
        if store.has_candidates(post.tweet_id):
            store.set_last_seen(uid, post.tweet_id)
            continue
        new_posts.append(post)
        store.set_last_seen(uid, post.tweet_id)

    if not new_posts:
        return 0
    # Newest first in the digest.
    new_posts.sort(key=lambda p: p.tweet_id, reverse=True)
    orch.handle_cycle(new_posts)
    return len(new_posts)


# ---------------------------------------------------------------------------
# Telegram listener
# ---------------------------------------------------------------------------
class TelegramListener(threading.Thread):
    """Long-polls Telegram for button taps and text replies.

    - callback `open:<tweet_id>`  -> send the post's detail card (full tweet + drafts)
    - callback `regen:<tweet_id>` -> regenerate that card in place
    - text message                -> conversational regenerate of the target post
      (the post you replied to, or the last one you opened)
    """

    def __init__(self, notifier, store: Store, orch: Orchestrator):
        super().__init__(daemon=True, name="tg-listener")
        self.notifier = notifier
        self.store = store
        self.orch = orch
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        if not hasattr(self.notifier, "get_updates"):
            return
        offset = int(self.store.get_meta("tg_offset", "0") or 0)
        if offset == 0:
            # First run: skip whatever is already queued (old /start, "hi", etc.)
            try:
                updates = self.notifier.get_updates(offset=0, timeout=0)
                if updates:
                    offset = int(updates[-1]["update_id"]) + 1
                    self.store.set_meta("tg_offset", str(offset))
            except Exception:
                pass
        log.info("telegram listener started (offset=%s)", offset)
        while not self._stop.is_set():
            try:
                updates = self.notifier.get_updates(offset=offset, timeout=25)
            except Exception as e:
                log.debug("getUpdates error: %s", e)
                time.sleep(5)
                continue
            for upd in updates:
                offset = int(upd["update_id"]) + 1
                self.store.set_meta("tg_offset", str(offset))
                try:
                    if "callback_query" in upd:
                        self._handle_callback(upd["callback_query"])
                    elif "message" in upd:
                        self._handle_message(upd["message"])
                except Exception as e:
                    log.error("update handling failed: %s", e)

    def _handle_callback(self, cb: dict) -> None:
        data = cb.get("data", "")
        cb_id = cb.get("id", "")
        msg = cb.get("message", {}) or {}

        if data.startswith("open:"):
            tid = data.split(":", 1)[1]
            self.notifier.answer_callback(cb_id)
            row = self.store.get_candidate_row(tid)
            if not row:
                return
            mid = self.notifier.send(row["post"], row["candidates"])
            if mid:
                self.store.map_message(mid, tid)
            self.store.set_meta("active_tweet", tid)

        elif data.startswith("regen:"):
            tid = data.split(":", 1)[1]
            self.notifier.answer_callback(cb_id, "重新生成中…")
            result = self.orch.regenerate(tid)
            if result:
                post, cands = result
                message_id = msg.get("message_id")
                if message_id and hasattr(self.notifier, "edit"):
                    self.notifier.edit(str(message_id), post, cands)
                    self.store.map_message(str(message_id), tid)
                self.store.set_meta("active_tweet", tid)
        else:
            self.notifier.answer_callback(cb_id)

    def _handle_message(self, msg: dict) -> None:
        text = (msg.get("text") or "").strip()
        if not text or text.startswith("/"):
            return
        # Which post is this steer about?
        tid = None
        reply = msg.get("reply_to_message")
        if reply:
            tid = self.store.tweet_for_message(str(reply.get("message_id")))
        if not tid:
            tid = self.store.get_meta("active_tweet", "") or None
        if not tid:
            self.notifier.send_text("先点开一条帖子（或回复某条详情消息），再告诉我怎么改～")
            return
        result = self.orch.regenerate(tid, instruction=text)
        if not result:
            return
        post, cands = result
        mid = self.notifier.send(post, cands)
        if mid:
            self.store.map_message(mid, tid)
        self.store.set_meta("active_tweet", tid)


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------
def _in_window(hour: int, start: int, end: int) -> bool:
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end  # window wraps midnight


def _seconds_to_next_start(now: datetime, start: int) -> float:
    target = now.replace(hour=start, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _interval_seconds(cfg: dict) -> float:
    poll = cfg.get("poll", {})
    minutes = float(poll.get("interval_minutes", 120))
    base = max(1.0, minutes) * 60.0
    if poll.get("jitter", True):
        base += random.uniform(-0.05, 0.05) * base
    return base


def _sleep(seconds: float, stop_event: threading.Event) -> None:
    waited = 0.0
    while waited < seconds and not stop_event.is_set():
        time.sleep(min(3.0, seconds - waited))
        waited += 3.0


def run_loop(
    cfg: dict,
    store: Store,
    twitter,
    orch: Orchestrator,
    on_cycle=None,
    stop_event: Optional[threading.Event] = None,
) -> None:
    """Blocking poll loop with an active time window. Ctrl-C / stop_event to exit."""
    stop_event = stop_event or threading.Event()
    poll = cfg.get("poll", {})
    tz = timezone(timedelta(hours=int(poll.get("timezone_offset", 8))))
    start = int(poll.get("active_start_hour", 12))
    end = int(poll.get("active_end_hour", 2))

    listener = None
    notifier = orch.notifier
    if getattr(notifier, "name", "") == "telegram" and notifier.configured():
        listener = TelegramListener(notifier, store, orch)
        listener.start()

    log.info(
        "poll loop: every %s min, active %02d:00–%02d:00 (UTC+%s)",
        poll.get("interval_minutes"), start, end, poll.get("timezone_offset", 8),
    )
    try:
        while not stop_event.is_set():
            now = datetime.now(tz)
            if _in_window(now.hour, start, end):
                try:
                    n = run_once(cfg, store, twitter, orch)
                    log.info("cycle done: %s new post(s)", n)
                    if on_cycle:
                        on_cycle(n)
                except Exception as e:
                    log.error("cycle error: %s", e)
                _sleep(_interval_seconds(cfg), stop_event)
            else:
                wait = _seconds_to_next_start(now, start)
                log.info("outside active window; sleeping %.1f h until %02d:00", wait / 3600, start)
                _sleep(wait, stop_event)
    finally:
        if listener:
            listener.stop()

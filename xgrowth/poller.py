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
    # Newest first.
    new_posts.sort(key=lambda p: p.tweet_id, reverse=True)
    # Cap per cycle so a backlog (or a very active watchlist) can't flood you.
    cap = int(poll.get("max_per_cycle", 8))
    dropped = 0
    if cap > 0 and len(new_posts) > cap:
        dropped = len(new_posts) - cap
        new_posts = new_posts[:cap]
    orch.handle_cycle(new_posts)
    if dropped:
        log.info("capped cycle: handled %s, skipped %s older new post(s)", len(new_posts), dropped)
        try:
            if orch.notifier.configured():
                orch.notifier.send_text(f"⚠️ 本轮新帖较多,已处理最新 {len(new_posts)} 条,跳过 {dropped} 条较旧的。")
        except Exception:
            pass
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
            forum = getattr(self.notifier, "mode", "dm") == "forum"
            # Forum mode: if this post already has a topic, just point the user to it.
            existing = self.store.thread_for_tweet(tid) if forum else None
            if existing and hasattr(self.notifier, "topic_link"):
                link = self.notifier.topic_link(int(existing))
                self.notifier.answer_callback(cb_id, "已为这条建过话题")
                if link:
                    self.notifier.send_text(f"↑ 这条已有话题：{link}")
                return
            self.notifier.answer_callback(cb_id, "正在生成回复…")
            result = self.orch.open_post(tid)  # lazy draft on first open
            if not result:
                return
            post, cands = result
            if forum and hasattr(self.notifier, "create_topic"):
                tid_thread = self.notifier.create_topic(self.notifier._topic_name(post))
                if tid_thread is not None:
                    self.store.map_topic(str(tid_thread), tid)
                    mid = self.notifier.send_to_topic(tid_thread, post, cands)
                    if mid:
                        self.store.map_message(str(mid), tid)
                    link = self.notifier.topic_link(tid_thread)
                    if link:
                        self.notifier.send_text(f"✅ 已建话题：{link}")
                    return
            # dm fallback
            mid = self.notifier.send(post, cands)
            if mid:
                self.store.map_message(str(mid), tid)
            self.store.set_meta("active_tweet", tid)

        elif data.startswith("del:"):
            tid = data.split(":", 1)[1]
            self.notifier.answer_callback(cb_id, "已删除话题")
            thread = msg.get("message_thread_id") or self.store.thread_for_tweet(tid)
            if thread is not None and hasattr(self.notifier, "delete_topic"):
                self.notifier.delete_topic(int(thread))
                self.store.unmap_topic(str(thread))
        else:
            self.notifier.answer_callback(cb_id)

    def _handle_message(self, msg: dict) -> None:
        text = (msg.get("text") or "").strip()
        if not text or text.startswith("/"):
            return
        # Which post is this steer about?
        tid = None
        thread = msg.get("message_thread_id")
        # forum mode: the Topic IS the post
        if thread is not None:
            tid = self.store.tweet_for_topic(str(thread))
        # reply-to a specific draft message
        if not tid:
            reply = msg.get("reply_to_message")
            if reply:
                tid = self.store.tweet_for_message(str(reply.get("message_id")))
        # DM fallback: the last opened post
        if not tid:
            tid = self.store.get_meta("active_tweet", "") or None
        if not tid:
            self.notifier.send_text("先点开一条帖子（或在它的话题里）再告诉我怎么改～")
            return
        result = self.orch.regenerate(tid, instruction=text)
        if not result:
            return
        post, cands = result
        if thread is not None and hasattr(self.notifier, "send_to_topic"):
            mid = self.notifier.send_to_topic(int(thread), post, cands, note=text)
        else:
            mid = self.notifier.send(post, cands, note=text)
            self.store.set_meta("active_tweet", tid)
        if mid:
            self.store.map_message(mid, tid)


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


def _cleanup_old_topics(cfg: dict, store: Store, notifier) -> None:
    """Delete forum topics older than `topic_ttl_hours` (default 24h ≈ yesterday's).

    Runs at most once per hour. No-op unless notifier is in forum mode.
    """
    if getattr(notifier, "mode", "dm") != "forum" or not hasattr(notifier, "delete_topic"):
        return
    ttl = int(cfg.get("poll", {}).get("topic_ttl_hours", 24))
    if ttl <= 0:
        return
    last = store.get_meta("last_topic_cleanup", "")
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        if last:
            last_dt = datetime.fromisoformat(last)
            if (datetime.now(timezone.utc) - last_dt).total_seconds() < 3600:
                return
    except Exception:
        pass
    store.set_meta("last_topic_cleanup", now_iso)
    old = store.topics_older_than(ttl)
    for thread_id in old:
        try:
            notifier.delete_topic(int(thread_id))
        except Exception:
            pass
        store.unmap_topic(str(thread_id))
    if old:
        log.info("cleaned up %s topic(s) older than %sh", len(old), ttl)


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
            _cleanup_old_topics(cfg, store, notifier)
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

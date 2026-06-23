"""SQLite-backed state: watchlist, seen tweets, generated candidates.

Single-file DB at ~/.xgrowth/xgrowth.db. Deliberately tiny and dependency-free
(stdlib sqlite3) so the engine can run anywhere.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import db_path, ensure_home
from .models import Candidate, Post, WatchEntry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    user_id            TEXT PRIMARY KEY,
    username           TEXT NOT NULL,
    enabled            INTEGER NOT NULL DEFAULT 1,
    last_seen_tweet_id TEXT NOT NULL DEFAULT '',
    followers          INTEGER NOT NULL DEFAULT 0,
    added_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id        TEXT NOT NULL,
    username        TEXT NOT NULL,
    author_id       TEXT NOT NULL DEFAULT '',
    tweet_text      TEXT NOT NULL,
    tweet_created   TEXT NOT NULL DEFAULT '',
    candidates_json TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    notified        INTEGER NOT NULL DEFAULT 0,
    message_id      TEXT NOT NULL DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_tweet ON candidates(tweet_id);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Maps a Telegram message id to the tweet it shows, so a user replying to that
-- message (conversational regenerate) can be routed to the right post.
CREATE TABLE IF NOT EXISTS tg_messages (
    message_id TEXT PRIMARY KEY,
    tweet_id   TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Maps a Telegram forum Topic (message_thread_id) to the tweet it's about, so a
-- reply anywhere in that topic routes to the right post (forum mode).
CREATE TABLE IF NOT EXISTS tg_topics (
    thread_id  TEXT PRIMARY KEY,
    tweet_id   TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: Optional[Path] = None):
        ensure_home()
        self.path = path or db_path()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---- watchlist -----------------------------------------------------
    def add_watch(self, user_id: str, username: str, followers: int = 0) -> None:
        self.conn.execute(
            """INSERT INTO watchlist (user_id, username, enabled, followers, added_at)
               VALUES (?, ?, 1, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
                                                  followers=excluded.followers,
                                                  enabled=1""",
            (str(user_id), username.lstrip("@"), int(followers), _now()),
        )
        self.conn.commit()

    def remove_watch(self, username: str) -> bool:
        username = username.lstrip("@")
        cur = self.conn.execute(
            "DELETE FROM watchlist WHERE username = ? COLLATE NOCASE", (username,)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def set_enabled(self, username: str, enabled: bool) -> bool:
        cur = self.conn.execute(
            "UPDATE watchlist SET enabled = ? WHERE username = ? COLLATE NOCASE",
            (1 if enabled else 0, username.lstrip("@")),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def set_last_seen(self, user_id: str, tweet_id: str) -> None:
        self.conn.execute(
            "UPDATE watchlist SET last_seen_tweet_id = ? WHERE user_id = ?",
            (str(tweet_id), str(user_id)),
        )
        self.conn.commit()

    def list_watch(self, only_enabled: bool = False) -> list[WatchEntry]:
        q = "SELECT * FROM watchlist"
        if only_enabled:
            q += " WHERE enabled = 1"
        q += " ORDER BY followers DESC, username ASC"
        rows = self.conn.execute(q).fetchall()
        return [
            WatchEntry(
                user_id=r["user_id"],
                username=r["username"],
                enabled=bool(r["enabled"]),
                last_seen_tweet_id=r["last_seen_tweet_id"],
                added_at=r["added_at"],
                followers=r["followers"],
            )
            for r in rows
        ]

    def get_watch_by_username(self, username: str) -> Optional[WatchEntry]:
        r = self.conn.execute(
            "SELECT * FROM watchlist WHERE username = ? COLLATE NOCASE", (username.lstrip("@"),)
        ).fetchone()
        if not r:
            return None
        return WatchEntry(
            user_id=r["user_id"],
            username=r["username"],
            enabled=bool(r["enabled"]),
            last_seen_tweet_id=r["last_seen_tweet_id"],
            added_at=r["added_at"],
            followers=r["followers"],
        )

    # ---- candidates ----------------------------------------------------
    def save_candidates(self, post: Post, candidates: list[Candidate]) -> int:
        payload = json.dumps([c.to_dict() for c in candidates], ensure_ascii=False)
        cur = self.conn.execute(
            """INSERT INTO candidates
               (tweet_id, username, author_id, tweet_text, tweet_created,
                candidates_json, created_at, notified)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0)
               ON CONFLICT(tweet_id) DO UPDATE SET candidates_json=excluded.candidates_json,
                                                   created_at=excluded.created_at""",
            (
                post.tweet_id,
                post.username,
                post.author_id,
                post.text,
                post.created_at,
                payload,
                _now(),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_candidates(self, tweet_id: str, candidates: list[Candidate]) -> None:
        payload = json.dumps([c.to_dict() for c in candidates], ensure_ascii=False)
        self.conn.execute(
            "UPDATE candidates SET candidates_json = ? WHERE tweet_id = ?",
            (payload, str(tweet_id)),
        )
        self.conn.commit()

    def mark_notified(self, tweet_id: str, message_id: str = "") -> None:
        self.conn.execute(
            "UPDATE candidates SET notified = 1, message_id = ? WHERE tweet_id = ?",
            (str(message_id), str(tweet_id)),
        )
        self.conn.commit()

    def has_candidates(self, tweet_id: str) -> bool:
        r = self.conn.execute(
            "SELECT 1 FROM candidates WHERE tweet_id = ?", (str(tweet_id),)
        ).fetchone()
        return r is not None

    def get_candidate_row(self, tweet_id: str) -> Optional[dict]:
        r = self.conn.execute(
            "SELECT * FROM candidates WHERE tweet_id = ?", (str(tweet_id),)
        ).fetchone()
        if not r:
            return None
        d = dict(r)
        d["candidates"] = [Candidate.from_dict(c) for c in json.loads(d["candidates_json"])]
        d["post"] = Post(
            tweet_id=d["tweet_id"],
            username=d["username"],
            author_id=d["author_id"],
            text=d["tweet_text"],
            created_at=d["tweet_created"],
        )
        return d

    def recent_candidates(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM candidates ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["candidates"] = [Candidate.from_dict(c) for c in json.loads(d["candidates_json"])]
            out.append(d)
        return out

    # ---- meta ----------------------------------------------------------
    def get_meta(self, key: str, default: str = "") -> str:
        r = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    # ---- telegram message <-> tweet mapping ----------------------------
    def map_message(self, message_id: str, tweet_id: str) -> None:
        self.conn.execute(
            "INSERT INTO tg_messages (message_id, tweet_id, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(message_id) DO UPDATE SET tweet_id=excluded.tweet_id",
            (str(message_id), str(tweet_id), _now()),
        )
        self.conn.commit()

    def tweet_for_message(self, message_id: str) -> Optional[str]:
        r = self.conn.execute(
            "SELECT tweet_id FROM tg_messages WHERE message_id = ?", (str(message_id),)
        ).fetchone()
        return r["tweet_id"] if r else None

    def map_topic(self, thread_id: str, tweet_id: str) -> None:
        self.conn.execute(
            "INSERT INTO tg_topics (thread_id, tweet_id, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(thread_id) DO UPDATE SET tweet_id=excluded.tweet_id",
            (str(thread_id), str(tweet_id), _now()),
        )
        self.conn.commit()

    def tweet_for_topic(self, thread_id: str) -> Optional[str]:
        r = self.conn.execute(
            "SELECT tweet_id FROM tg_topics WHERE thread_id = ?", (str(thread_id),)
        ).fetchone()
        return r["tweet_id"] if r else None

    def thread_for_tweet(self, tweet_id: str) -> Optional[str]:
        r = self.conn.execute(
            "SELECT thread_id FROM tg_topics WHERE tweet_id = ?", (str(tweet_id),)
        ).fetchone()
        return r["thread_id"] if r else None

    def unmap_topic(self, thread_id: str) -> None:
        self.conn.execute("DELETE FROM tg_topics WHERE thread_id = ?", (str(thread_id),))
        self.conn.commit()

    def topics_older_than(self, hours: int) -> list[str]:
        """thread_ids created more than `hours` ago (for daily cleanup)."""
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = self.conn.execute(
            "SELECT thread_id FROM tg_topics WHERE created_at < ?", (cutoff,)
        ).fetchall()
        return [r["thread_id"] for r in rows]

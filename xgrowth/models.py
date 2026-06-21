"""Core data models passed between the poller, engine, and notifiers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Post:
    """A single tweet we might want to reply to."""

    tweet_id: str
    username: str
    author_id: str
    text: str
    created_at: str = ""

    @property
    def url(self) -> str:
        return f"https://x.com/{self.username}/status/{self.tweet_id}"

    def to_dict(self) -> dict:
        return {
            "tweet_id": self.tweet_id,
            "username": self.username,
            "author_id": self.author_id,
            "text": self.text,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Post":
        return cls(
            tweet_id=str(d["tweet_id"]),
            username=d["username"],
            author_id=str(d.get("author_id", "")),
            text=d.get("text", ""),
            created_at=d.get("created_at", ""),
        )


@dataclass
class Candidate:
    """One drafted reply in a given style."""

    style: str
    text: str

    def to_dict(self) -> dict:
        return {"style": self.style, "text": self.text}

    @classmethod
    def from_dict(cls, d: dict) -> "Candidate":
        return cls(style=str(d.get("style", "")).strip(), text=str(d.get("text", "")).strip())


@dataclass
class WatchEntry:
    """An account being monitored."""

    user_id: str
    username: str
    enabled: bool = True
    last_seen_tweet_id: str = ""
    added_at: str = ""
    followers: int = field(default=0)

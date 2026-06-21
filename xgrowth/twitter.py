"""Twitter / X data access, with two interchangeable providers.

  - rapidapi : a third-party RapidAPI proxy (default; e.g. twitter241). Cheap,
               generous limits, and `get-users-v2` returns each user's latest
               tweet inline — so we poll the whole watchlist in ONE call.
  - official : the official X API v2 (api.twitter.com, Bearer token).

Both expose the same interface used by the poller:
    get_user(username)            -> TwitterUser
    get_following(user_id)        -> list[TwitterUser]
    latest_for(user_ids, ...)     -> dict[user_id -> Post]   (one Post: newest qualifying tweet)

Select via config: twitter.provider = rapidapi | official.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, Optional

import httpx

from .models import Post


class TwitterError(RuntimeError):
    pass


class RateLimited(TwitterError):
    def __init__(self, reset_epoch: int = 0):
        self.reset_epoch = reset_epoch
        super().__init__(f"rate limited (resets at {reset_epoch})")


@dataclass
class TwitterUser:
    id: str
    username: str
    name: str = ""
    followers: int = 0


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


# ---------------------------------------------------------------------------
# RapidAPI provider (twitter241-compatible)
# ---------------------------------------------------------------------------
class RapidApiClient:
    """Talks to a RapidAPI Twitter proxy. Defaults to the twitter241 schema."""

    def __init__(self, api_key: str, host: str = "twitter241.p.rapidapi.com", timeout: float = 25.0):
        if not api_key:
            raise TwitterError("missing twitter.rapidapi_key — set it in config.yaml")
        self.host = host
        self._client = httpx.Client(
            base_url=f"https://{host}",
            headers={
                "x-rapidapi-key": api_key,
                "x-rapidapi-host": host,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "RapidApiClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        resp = self._client.get(path, params=params or {})
        if resp.status_code == 429:
            raise RateLimited(int(resp.headers.get("x-ratelimit-reset", "0") or 0))
        if resp.status_code >= 400:
            raise TwitterError(f"{resp.status_code} {path}: {resp.text[:300]}")
        return resp.json()

    # ---- user resolution (GraphQL /user) ------------------------------
    def get_user(self, username: str) -> TwitterUser:
        username = username.lstrip("@")
        data = self._get("/user", {"username": username})
        try:
            res = data["result"]["data"]["user"]["result"]
        except (KeyError, TypeError):
            raise TwitterError(f"user @{username} not found")
        core = res.get("core", {}) or {}
        legacy = res.get("legacy", {}) or {}
        screen = core.get("screen_name") or legacy.get("screen_name") or username
        name = core.get("name") or legacy.get("name") or ""
        followers = int(legacy.get("followers_count", 0) or 0)
        rest_id = res.get("rest_id") or legacy.get("id_str") or ""
        if not rest_id:
            raise TwitterError(f"could not resolve id for @{username}")
        return TwitterUser(id=str(rest_id), username=screen, name=name, followers=followers)

    # ---- batched latest-tweet poll (/get-users-v2) --------------------
    def latest_for(
        self,
        user_ids: list[str],
        exclude_replies: bool = True,
        exclude_retweets: bool = True,
    ) -> dict[str, Post]:
        out: dict[str, Post] = {}
        # get-users-v2 accepts up to 100 ids per call (verified: 100 ok, 200 -> 404).
        for chunk in _chunks([str(u) for u in user_ids], 100):
            data = self._get("/get-users-v2", {"users": ",".join(chunk)})
            for u in data.get("result", []) or []:
                uid = str(u.get("id_str") or u.get("id") or "")
                if not uid:
                    continue
                post = self._post_from_status(
                    u.get("status"),
                    u.get("screen_name", ""),
                    uid,
                    exclude_replies,
                    exclude_retweets,
                )
                if post:
                    out[uid] = post
        return out

    @staticmethod
    def _post_from_status(
        st: Optional[dict],
        screen: str,
        uid: str,
        exclude_replies: bool,
        exclude_retweets: bool,
    ) -> Optional[Post]:
        if not st or not isinstance(st, dict):
            return None
        text = st.get("full_text") or st.get("text") or ""
        is_rt = bool(st.get("retweeted_status")) or text.startswith("RT @")
        is_reply = bool(st.get("in_reply_to_status_id_str") or st.get("in_reply_to_screen_name"))
        if exclude_retweets and is_rt:
            return None
        if exclude_replies and is_reply:
            return None
        tid = str(st.get("id_str") or st.get("id") or "")
        if not tid:
            return None
        return Post(
            tweet_id=tid,
            username=screen,
            author_id=uid,
            text=text,
            created_at=st.get("created_at", ""),
        )

    # ---- following list (/followings, GraphQL timeline) ---------------
    def get_following(self, user_id: str, max_pages: int = 5, count: int = 50) -> list[TwitterUser]:
        out: list[TwitterUser] = []
        cursor: Optional[str] = None
        seen: set[str] = set()
        for _ in range(max_pages):
            params = {"user": str(user_id), "count": count}
            if cursor:
                params["cursor"] = cursor
            data = self._get("/followings", params)
            users, next_cursor = self._parse_following(data)
            new = 0
            for u in users:
                if u.id in seen:
                    continue
                seen.add(u.id)
                out.append(u)
                new += 1
            if not next_cursor or new == 0:
                break
            cursor = next_cursor
            time.sleep(0.6)
        return out

    @staticmethod
    def _parse_following(data: dict) -> tuple[list[TwitterUser], Optional[str]]:
        users: list[TwitterUser] = []
        next_cursor: Optional[str] = None
        try:
            instructions = data["result"]["timeline"]["instructions"]
        except (KeyError, TypeError):
            return users, (data.get("cursor", {}) or {}).get("bottom")
        for instr in instructions:
            for entry in instr.get("entries", []) or []:
                content = entry.get("content", {}) or {}
                if content.get("cursorType") == "Bottom" or content.get("entryType") == "TimelineTimelineCursor":
                    if content.get("cursorType") == "Bottom":
                        next_cursor = content.get("value")
                    continue
                item = content.get("itemContent", {}) or {}
                res = (item.get("user_results", {}) or {}).get("result", {}) or {}
                if not res:
                    continue
                core = res.get("core", {}) or {}
                legacy = res.get("legacy", {}) or {}
                rest_id = res.get("rest_id") or legacy.get("id_str")
                screen = core.get("screen_name") or legacy.get("screen_name")
                if not rest_id or not screen:
                    continue
                users.append(
                    TwitterUser(
                        id=str(rest_id),
                        username=screen,
                        name=core.get("name") or legacy.get("name") or "",
                        followers=int(legacy.get("followers_count", 0) or 0),
                    )
                )
        # cursor can also live at top level
        if not next_cursor:
            next_cursor = (data.get("cursor", {}) or {}).get("bottom")
        return users, next_cursor


# ---------------------------------------------------------------------------
# Official X API v2 provider
# ---------------------------------------------------------------------------
class OfficialTwitterClient:
    BASE = "https://api.twitter.com/2"

    def __init__(self, bearer_token: str, timeout: float = 20.0):
        if not bearer_token:
            raise TwitterError("missing twitter.bearer_token — set it in config.yaml")
        self._client = httpx.Client(
            base_url=self.BASE,
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OfficialTwitterClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        resp = self._client.get(path, params=params or {})
        if resp.status_code == 429:
            raise RateLimited(int(resp.headers.get("x-rate-limit-reset", "0") or 0))
        if resp.status_code >= 400:
            raise TwitterError(f"{resp.status_code} {path}: {resp.text[:300]}")
        return resp.json()

    def get_user(self, username: str) -> TwitterUser:
        username = username.lstrip("@")
        data = self._get(f"/users/by/username/{username}", {"user.fields": "public_metrics"})
        u = data.get("data")
        if not u:
            raise TwitterError(f"user @{username} not found")
        m = u.get("public_metrics", {})
        return TwitterUser(
            id=str(u["id"]), username=u["username"], name=u.get("name", ""),
            followers=int(m.get("followers_count", 0)),
        )

    def _recent(self, user_id: str, exclude_replies: bool, exclude_retweets: bool) -> list[Post]:
        exclude = []
        if exclude_replies:
            exclude.append("replies")
        if exclude_retweets:
            exclude.append("retweets")
        params: dict = {"max_results": 5, "tweet.fields": "created_at,author_id"}
        if exclude:
            params["exclude"] = ",".join(exclude)
        data = self._get(f"/users/{user_id}/tweets", params)
        out = []
        for t in data.get("data", []) or []:
            out.append(
                Post(tweet_id=str(t["id"]), username="", author_id=str(t.get("author_id", user_id)),
                     text=t.get("text", ""), created_at=t.get("created_at", ""))
            )
        return out

    def latest_for(self, user_ids, exclude_replies=True, exclude_retweets=True) -> dict[str, Post]:
        out: dict[str, Post] = {}
        for uid in user_ids:
            try:
                tweets = self._recent(str(uid), exclude_replies, exclude_retweets)
            except RateLimited:
                raise
            except TwitterError:
                continue
            if tweets:
                out[str(uid)] = tweets[0]
        return out

    def get_following(self, user_id: str, max_pages: int = 5) -> list[TwitterUser]:
        out: list[TwitterUser] = []
        token = None
        for _ in range(max_pages):
            params = {"max_results": 1000, "user.fields": "public_metrics"}
            if token:
                params["pagination_token"] = token
            data = self._get(f"/users/{user_id}/following", params)
            for u in data.get("data", []) or []:
                m = u.get("public_metrics", {})
                out.append(TwitterUser(id=str(u["id"]), username=u["username"],
                                       name=u.get("name", ""), followers=int(m.get("followers_count", 0))))
            token = data.get("meta", {}).get("next_token")
            if not token:
                break
            time.sleep(1)
        return out


# ---------------------------------------------------------------------------
def build_twitter(cfg: dict):
    """Construct the configured Twitter provider from the `twitter` config block."""
    tc = cfg.get("twitter", {})
    provider = (tc.get("provider") or "rapidapi").lower()
    if provider == "rapidapi":
        return RapidApiClient(
            tc.get("rapidapi_key", ""),
            host=tc.get("rapidapi_host", "twitter241.p.rapidapi.com"),
        )
    if provider == "official":
        return OfficialTwitterClient(tc.get("bearer_token", ""))
    raise TwitterError(f"unknown twitter.provider: {provider!r} (expected rapidapi|official)")


# Back-compat alias.
TwitterClient = OfficialTwitterClient

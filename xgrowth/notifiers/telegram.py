"""Telegram notifier with inline buttons.

Card layout sent to the user's phone:

    🐦 @naval · just now
    "<original tweet text>"
    ─────────────
    ① 神补刀
    <reply candidate 1>

    ② 反直觉
    <reply candidate 2>
    ─────────────
    [📋 复制①] [📋 复制②] ...      <- copy_text buttons (no typing needed)
    [🔄 换一批]  [🔗 看原帖]

Buttons:
- 📋 复制 — Telegram `copy_text` button: tap copies the reply to clipboard.
- 🔄 换一批 — callback_data `regen:<tweet_id>`, handled by the running engine's
  Telegram listener (see poller.TelegramListener).
- 🔗 看原帖 — url button to the tweet.

`copy_text` inline buttons require a reasonably recent Telegram app (Bot API
7.11+, late 2024). If a user's app is older the button is simply ignored.
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from ..models import Candidate, Post
from ..util import human_age, truncate
from .base import Notifier, NotifierError

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
CST = timezone(timedelta(hours=8))  # Beijing time, for the digest header
MAX_DIGEST_ITEMS = 90  # Telegram inline-keyboard button ceiling guard


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str, timeout: float = 20.0):
        self.bot_token = bot_token or ""
        self.chat_id = str(chat_id or "")
        self._timeout = timeout

    def configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    # ---- HTTP ----------------------------------------------------------
    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/{method}"

    def _call(self, method: str, payload: dict) -> dict:
        if not self.bot_token:
            raise NotifierError("missing telegram bot_token")
        resp = httpx.post(self._url(method), json=payload, timeout=self._timeout)
        data = resp.json()
        if not data.get("ok"):
            raise NotifierError(f"telegram {method} failed: {data.get('description')}")
        return data.get("result", {})

    # ---- rendering -----------------------------------------------------
    @staticmethod
    def _circle(i: int) -> str:
        return CIRCLED[i] if i < len(CIRCLED) else f"({i + 1})"

    def _format(self, post: Post, candidates: list[Candidate]) -> str:
        age = human_age(post.created_at)
        head = f"🐦 <b>@{html.escape(post.username)}</b>" + (f" · {age}" if age else "")
        lines = [head]
        lines.append(f"<i>{html.escape(post.text)}</i>")
        lines.append("─────────────")
        for i, c in enumerate(candidates):
            label = f"{self._circle(i)} {html.escape(c.style)}".strip()
            lines.append(f"<b>{label}</b>")
            lines.append(html.escape(c.text))
            lines.append("")
        lines.append("💬 <i>直接回复本条消息可让我改（例：更毒一点 / 更短 / 换个梗）</i>")
        return "\n".join(lines).strip()

    def _keyboard(self, post: Post, candidates: list[Candidate]) -> dict:
        copy_row = []
        for i, c in enumerate(candidates):
            copy_row.append(
                {
                    "text": f"📋 复制{self._circle(i)}",
                    "copy_text": {"text": c.text[:256]},  # Telegram caps copy_text at 256
                }
            )
        # Telegram allows max 8 buttons per row; chunk the copy buttons.
        rows = [copy_row[j : j + 4] for j in range(0, len(copy_row), 4)]
        rows.append(
            [
                {"text": "🔄 换一批", "callback_data": f"regen:{post.tweet_id}"},
                {"text": "🔗 看原帖", "url": post.url},
            ]
        )
        return {"inline_keyboard": rows}

    # ---- Notifier API --------------------------------------------------
    def send(self, post: Post, candidates: list[Candidate]) -> Optional[str]:
        result = self._call(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": self._format(post, candidates),
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": self._keyboard(post, candidates),
            },
        )
        return str(result.get("message_id", "")) or None

    def edit(self, message_id: str, post: Post, candidates: list[Candidate]) -> None:
        self._call(
            "editMessageText",
            {
                "chat_id": self.chat_id,
                "message_id": int(message_id),
                "text": self._format(post, candidates),
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": self._keyboard(post, candidates),
            },
        )

    def send_text(self, text: str) -> Optional[str]:
        result = self._call(
            "sendMessage",
            {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True},
        )
        return str(result.get("message_id", "")) or None

    # ---- digest (the "merged forward" collection) ----------------------
    def send_digest(self, items: list[dict]) -> Optional[str]:
        """One index message for a whole poll cycle.

        items: [{"post": Post, "candidates": [Candidate, ...]}, ...]
        Each gets a button that drills into the full post + reply suggestions.
        """
        items = items[:MAX_DIGEST_ITEMS]
        now = datetime.now(CST).strftime("%H:%M")
        header = f"🗂 <b>本轮 {len(items)} 条新帖</b> · {now}（北京时间）"
        lines = [header]
        buttons = []
        for i, it in enumerate(items):
            post: Post = it["post"]
            c = self._circle(i)
            age = human_age(post.created_at)
            agetxt = f" · {age}" if age else ""
            if i < 30:  # keep the text body well under Telegram's 4096 cap
                snippet = html.escape(truncate(post.text, 70))
                lines.append(f"\n{c} <b>@{html.escape(post.username)}</b>{agetxt}\n{snippet}")
            uname = post.username[:14]
            buttons.append({"text": f"{c} @{uname}", "callback_data": f"open:{post.tweet_id}"})
        lines.append("\n\n👇 点按钮看全文 + 回复建议")
        rows = [buttons[j : j + 2] for j in range(0, len(buttons), 2)]
        result = self._call(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": "\n".join(lines),
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": {"inline_keyboard": rows},
            },
        )
        return str(result.get("message_id", "")) or None

    # ---- listener helpers (used by poller.TelegramListener) ------------
    def get_updates(self, offset: int = 0, timeout: int = 25) -> list[dict]:
        resp = httpx.get(
            self._url("getUpdates"),
            params={
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": '["callback_query","message"]',
            },
            timeout=timeout + 10,
        )
        data = resp.json()
        if not data.get("ok"):
            raise NotifierError(f"telegram getUpdates failed: {data.get('description')}")
        return data.get("result", [])

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        try:
            self._call(
                "answerCallbackQuery",
                {"callback_query_id": callback_id, "text": text},
            )
        except NotifierError:
            pass

    def discover_chat_id(self) -> Optional[str]:
        """Read recent updates to find a chat id (for first-time setup)."""
        resp = httpx.get(self._url("getUpdates"), params={"timeout": 0}, timeout=15)
        data = resp.json()
        if not data.get("ok"):
            raise NotifierError(f"telegram getUpdates failed: {data.get('description')}")
        for upd in reversed(data.get("result", [])):
            msg = upd.get("message") or upd.get("edited_message") or {}
            chat = msg.get("chat") or {}
            if chat.get("id"):
                return str(chat["id"])
        return None

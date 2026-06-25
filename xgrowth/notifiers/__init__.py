"""Notifier adapters: push reply candidates to the user's phone."""

from __future__ import annotations

from .base import Notifier, NotifierError
from .telegram import TelegramNotifier
from .lark import LarkNotifier
from .bark import BarkNotifier


def build_notifier(cfg: dict) -> Notifier:
    nc = cfg.get("notify", {})
    provider = (nc.get("provider") or "telegram").lower()
    if provider == "telegram":
        tg = nc.get("telegram", {})
        lang = cfg.get("language", "en")
        # A friendly tz label for the digest time, only shown for zh (Beijing).
        offset = cfg.get("poll", {}).get("timezone_offset", 8)
        tz_label = ""
        if lang == "zh" and offset == 8:
            tz_label = "（北京时间）"
        elif offset is not None:
            sign = "+" if offset >= 0 else ""
            tz_label = f"UTC{sign}{offset}"
        return TelegramNotifier(
            tg.get("bot_token", ""), tg.get("chat_id", ""),
            mode=tg.get("mode", "dm"), lang=lang, tz_label=tz_label,
        )
    if provider == "lark":
        return LarkNotifier(nc.get("lark", {}).get("webhook_url", ""))
    if provider == "bark":
        b = nc.get("bark", {})
        return BarkNotifier(b.get("server", "https://api.day.app"), b.get("device_key", ""))
    raise NotifierError(f"unknown notify.provider: {provider!r}")


__all__ = [
    "Notifier",
    "NotifierError",
    "TelegramNotifier",
    "LarkNotifier",
    "BarkNotifier",
    "build_notifier",
]

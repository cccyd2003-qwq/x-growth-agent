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
        return TelegramNotifier(tg.get("bot_token", ""), tg.get("chat_id", ""))
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

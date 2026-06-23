"""Configuration + paths.

State and secrets live OUTSIDE the repo, under ~/.xgrowth (override with the
XGROWTH_HOME env var). Nothing here is ever committed.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "twitter": {
        # provider: rapidapi (default) | official
        "provider": "rapidapi",
        # RapidAPI proxy (e.g. twitter241). Cheap, generous limits.
        "rapidapi_key": "",
        "rapidapi_host": "twitter241.p.rapidapi.com",
        # Official X API v2 (only used when provider = official).
        "bearer_token": "",
    },
    "poll": {
        "interval_minutes": 120,
        "jitter": True,
        # Only poll inside this daily window (avoids burning API quota overnight).
        # Hours are in the configured timezone offset; window may wrap midnight.
        "timezone_offset": 8,        # UTC+8 = Beijing
        "active_start_hour": 12,     # 12:00 noon
        "active_end_hour": 2,        # until 02:00 next day
        "max_per_account": 5,
        # Hard cap on how many new posts to handle per cycle, so a backlog or a
        # very active watchlist can't flood you with topics. Older overflow is skipped.
        "max_per_cycle": 8,
        # forum mode: auto-delete topics older than this many hours (daily cleanup).
        "topic_ttl_hours": 24,
        "exclude_replies": True,
        "exclude_retweets": True,
    },
    "engine": {
        "provider": "claude",
        "model": "claude-opus-4-8",
        "claude_path": "claude",
        "codex_path": "codex",
        "num_candidates": 3,
        "styles": ["神补刀", "反直觉", "一句戳中"],
        "timeout_seconds": 120,
    },
    "notify": {
        "provider": "telegram",
        "telegram": {"bot_token": "", "chat_id": "", "mode": "dm"},
        "lark": {"webhook_url": ""},
        "bark": {"server": "https://api.day.app", "device_key": ""},
    },
    "panel": {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 7777,
    },
}


def home_dir() -> Path:
    """Root directory for all xgrowth runtime data."""
    env = os.environ.get("XGROWTH_HOME")
    base = Path(env).expanduser() if env else Path.home() / ".xgrowth"
    return base


def config_path() -> Path:
    return home_dir() / "config.yaml"


def db_path() -> Path:
    return home_dir() / "xgrowth.db"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into a copy of base."""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def ensure_home() -> Path:
    d = home_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_exists() -> bool:
    return config_path().exists()


def load_config() -> dict:
    """Load config, layering the user's file on top of defaults."""
    path = config_path()
    user: dict = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
    cfg = _deep_merge(DEFAULT_CONFIG, user)
    # Allow env overrides for the most sensitive / CI-relevant values.
    if os.environ.get("XGROWTH_TWITTER_BEARER"):
        cfg["twitter"]["bearer_token"] = os.environ["XGROWTH_TWITTER_BEARER"]
    if os.environ.get("XGROWTH_RAPIDAPI_KEY"):
        cfg["twitter"]["rapidapi_key"] = os.environ["XGROWTH_RAPIDAPI_KEY"]
    if os.environ.get("XGROWTH_TELEGRAM_TOKEN"):
        cfg["notify"]["telegram"]["bot_token"] = os.environ["XGROWTH_TELEGRAM_TOKEN"]
    if os.environ.get("XGROWTH_TELEGRAM_CHAT"):
        cfg["notify"]["telegram"]["chat_id"] = os.environ["XGROWTH_TELEGRAM_CHAT"]
    return cfg


def save_config(cfg: dict) -> Path:
    ensure_home()
    path = config_path()
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    return path


def write_default_config(force: bool = False) -> Path:
    """Create a fresh config.yaml from defaults if one doesn't exist."""
    path = config_path()
    if path.exists() and not force:
        return path
    return save_config(copy.deepcopy(DEFAULT_CONFIG))

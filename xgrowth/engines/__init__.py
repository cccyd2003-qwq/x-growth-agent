"""Brain adapters: drive a local coding agent (Claude Code / Codex) headlessly."""

from __future__ import annotations

from typing import Optional

from .base import Engine, EngineError
from .claude import ClaudeEngine
from .codex import CodexEngine


def build_engine(cfg: dict) -> Engine:
    """Construct the configured engine from the `engine` config block."""
    ec = cfg.get("engine", {})
    provider = (ec.get("provider") or "claude").lower()
    model = ec.get("model") or None
    timeout = int(ec.get("timeout_seconds", 120))
    if provider == "claude":
        return ClaudeEngine(path=ec.get("claude_path", "claude"), model=model, timeout=timeout)
    if provider == "codex":
        return CodexEngine(path=ec.get("codex_path", "codex"), model=model, timeout=timeout)
    raise EngineError(f"unknown engine.provider: {provider!r} (expected claude|codex)")


__all__ = ["Engine", "EngineError", "ClaudeEngine", "CodexEngine", "build_engine"]

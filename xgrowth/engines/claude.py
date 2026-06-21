"""Claude Code adapter — runs `claude -p` headlessly.

Uses the user's existing Claude Code install: their login, their model, their
config. We never touch API keys here.
"""

from __future__ import annotations

import json
import subprocess
from typing import Optional

from .base import Engine, EngineError


class ClaudeEngine(Engine):
    name = "claude"

    def _run(self, prompt: str) -> str:
        cmd = [self.path, "-p", prompt, "--output-format", "json"]
        if self.model:
            cmd += ["--model", self.model]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
            )
        except FileNotFoundError as e:
            raise EngineError(
                f"`{self.path}` not found. Is Claude Code installed and on PATH?"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise EngineError(f"claude timed out after {self.timeout}s") from e

        if proc.returncode != 0:
            raise EngineError(
                f"claude exited {proc.returncode}: {(proc.stderr or proc.stdout)[:400]}"
            )

        stdout = proc.stdout.strip()
        # `--output-format json` wraps the result: {"type":"result","result":"...",...}
        try:
            outer = json.loads(stdout)
            if isinstance(outer, dict) and "result" in outer:
                return str(outer["result"])
        except Exception:
            pass
        # Fall back to raw stdout; the base parser will dig the JSON out.
        return stdout

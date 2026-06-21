"""Codex adapter — runs `codex exec` headlessly.

`codex exec <prompt>` runs non-interactively and prints the final assistant
message to stdout. We then dig the JSON payload out of that text.
"""

from __future__ import annotations

import subprocess
from typing import Optional

from .base import Engine, EngineError


class CodexEngine(Engine):
    name = "codex"

    def _run(self, prompt: str) -> str:
        # --skip-git-repo-check so it runs anywhere; quiet noise on stderr.
        cmd = [self.path, "exec", "--skip-git-repo-check"]
        if self.model:
            cmd += ["--model", self.model]
        cmd.append(prompt)
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
                f"`{self.path}` not found. Is the Codex CLI installed and on PATH?"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise EngineError(f"codex timed out after {self.timeout}s") from e

        if proc.returncode != 0:
            raise EngineError(
                f"codex exited {proc.returncode}: {(proc.stderr or proc.stdout)[:400]}"
            )

        # Codex prints session chatter then the final message. The base parser's
        # balanced-brace scan pulls the JSON object out of the tail.
        return proc.stdout.strip()

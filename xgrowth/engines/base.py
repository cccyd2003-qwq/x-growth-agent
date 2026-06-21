"""Engine interface + shared parsing of the model's JSON reply payload."""

from __future__ import annotations

from typing import Optional

from ..models import Candidate, Post
from ..prompts import build_reply_prompt
from ..util import extract_json


class EngineError(RuntimeError):
    pass


class Engine:
    name = "base"

    def __init__(self, path: str, model: Optional[str] = None, timeout: int = 120):
        self.path = path
        self.model = model
        self.timeout = timeout

    # Subclasses implement the actual headless call and return raw stdout text.
    def _run(self, prompt: str) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def available(self) -> bool:  # pragma: no cover - trivial
        import shutil

        return shutil.which(self.path) is not None

    def generate(
        self,
        post: Post,
        styles: list[str],
        num_candidates: int,
        persona: Optional[str] = None,
        instruction: Optional[str] = None,
    ) -> list[Candidate]:
        prompt = build_reply_prompt(
            post, styles, num_candidates, persona=persona, instruction=instruction
        )
        raw = self._run(prompt)
        return self._parse(raw, num_candidates)

    @staticmethod
    def _parse(raw: str, num_candidates: int) -> list[Candidate]:
        data = extract_json(raw)
        items = None
        if isinstance(data, dict):
            items = data.get("candidates")
        elif isinstance(data, list):
            items = data
        if not isinstance(items, list) or not items:
            raise EngineError(f"could not parse candidates from engine output:\n{raw[:500]}")
        out: list[Candidate] = []
        for it in items:
            if isinstance(it, dict):
                out.append(Candidate.from_dict(it))
            elif isinstance(it, str):
                out.append(Candidate(style="", text=it.strip()))
        out = [c for c in out if c.text]
        if not out:
            raise EngineError("engine returned no usable reply text")
        return out[:num_candidates] if num_candidates else out

"""Prompt construction for the reply-drafting brain.

The whole product lives or dies on whether the replies are *interesting*. This
module encodes the anti-AI-slop rules and loads few-shot examples so any engine
(claude/codex) produces the same house style.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import Post

# Examples ship inside the repo so the brain has a baseline voice even before
# the user grows their own library.
_EXAMPLES_PATH = Path(__file__).resolve().parent.parent / "examples" / "replies.jsonl"

SYSTEM_RULES = """\
You are a sharp, very-online ghostwriter helping someone grow from 0 to 1 on X
(Twitter) by replying to bigger accounts. A reply only matters if it gets
NOTICED: it must be funny, meme-y, contrarian-but-smart, or a genuinely sharp
question. Generic agreement is worthless.

HARD RULES (break these and the reply is a failure):
- Match the post's language. If the post is English, reply in English.
- VERY SHORT. Hard cap 20 words; aim for 10-15; 3-5 words can win. Never pad.
  Write like a real person firing off a quick reply on their phone.
- BANNED phrases/moves: "Great point", "Well said", "Indeed", "As an AI",
  "This.", "100%", "Couldn't agree more", corporate cheerleading, hashtag spam,
  emoji soup, summarizing what they already said.
- Casual register. lowercase is fine. fragments are fine. a single emoji is the
  max, and only if it lands.
- Be specific to THIS post. Add a new angle, a joke, a twist, or a real question.
- No slurs, no harassment, nothing that would get the account suspended.
"""


def _load_examples(limit: int = 6) -> list[dict]:
    if not _EXAMPLES_PATH.exists():
        return []
    rows: list[dict] = []
    with open(_EXAMPLES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows[:limit]


def _format_examples(rows: list[dict]) -> str:
    if not rows:
        return "(no examples yet)"
    blocks = []
    for r in rows:
        post = r.get("post", "")
        reply = r.get("reply", "")
        style = r.get("style", "")
        tag = f" [{style}]" if style else ""
        blocks.append(f'POST: "{post}"\nGOOD REPLY{tag}: "{reply}"')
    return "\n\n".join(blocks)


def build_reply_prompt(
    post: Post,
    styles: list[str],
    num_candidates: int,
    persona: Optional[str] = None,
    extra_examples: Optional[list[dict]] = None,
    instruction: Optional[str] = None,
) -> str:
    """Assemble the full single-shot prompt sent to the coding agent.

    `instruction` is an optional free-text steer from the user (e.g. "更毒一点",
    "make it funnier", "shorter") used for conversational regeneration.
    """
    examples = _load_examples()
    if extra_examples:
        examples = (extra_examples + examples)[:8]

    style_list = ", ".join(styles) if styles else "free"
    persona_block = ""
    if persona:
        persona_block = (
            "\nWHO IS REPLYING (write in this person's voice):\n" + persona.strip() + "\n"
        )

    instruction_block = ""
    if instruction:
        instruction_block = (
            "\nEXTRA STEER FROM THE USER — apply this above all (still obey the hard "
            f"rules and the 20-word cap):\n{instruction.strip()}\n"
        )

    return f"""{SYSTEM_RULES}
{persona_block}{instruction_block}
Produce exactly {num_candidates} candidate replies. Rotate through these styles,
one per candidate where possible: {style_list}.

Few-shot examples of the bar you're aiming for:
{_format_examples(examples)}

THE POST YOU ARE REPLYING TO:
@{post.username}: "{post.text}"

Return STRICT JSON and nothing else — no prose, no markdown, no code fences:
{{"candidates": [{{"style": "<style label>", "text": "<the reply>"}}]}}
"""

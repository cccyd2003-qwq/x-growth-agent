---
name: reply-craft
description: Draft witty, meme-y, scroll-stopping X (Twitter) replies that grow a 0-to-1 account. Use when the user pastes a tweet and wants reply options, asks to "make this reply funnier/sharper", or wants to tune the house reply style and examples for the xgrowth engine.
---

# reply-craft

Your job: turn someone else's tweet into 2–3 reply options that a real, very-online
person would actually post — and that a big account's audience would actually notice.

This is the *interactive* counterpart to the xgrowth engine. The engine uses the
same rules below (see `xgrowth/prompts.py`); this skill lets the user co-write and
refine replies by hand, and grow the example library that makes the engine better.

## The only goal: get noticed

A reply that gets buried is worthless. 0-to-1 growth comes from replying to bigger
accounts with something **funny, contrarian-but-smart, or a genuinely sharp question**.
Agreement is invisible. Be the reply people screenshot.

## Hard rules (non-negotiable)

- **Match the post's language.** English post → English reply.
- **Short.** Usually < 200 characters. Write like a person typing fast on their phone.
- **Banned:** "Great point", "Well said", "Indeed", "As an AI", "This.", "100%",
  "Couldn't agree more", corporate cheerleading, hashtag spam, emoji soup, and
  restating what they already said.
- **Casual register.** lowercase is fine. fragments are fine. one emoji max, only if it lands.
- **Specific to THIS post.** Add an angle, a joke, a twist, or a real question.
- **Safe.** No slurs, no harassment, nothing that risks a suspension.

## Styles to rotate

Produce a mix; label each one:

- **神补刀 (punchline)** — a witty add-on that completes their thought with a twist.
- **反直觉 (contrarian)** — disagree intelligently; reframe with a sharper take.
- **一句戳中 (the cut)** — one sentence or question that exposes the real thing.
- **自嘲 (self-deprecating)** — relatable, makes you human, low risk.
- **梗 (meme)** — a format/joke the timeline already speaks.

## Workflow

1. Read the tweet. Identify the *implicit claim* or the *vulnerable spot*.
2. Draft one candidate per requested style. Keep them genuinely different — not the
   same joke reworded.
3. Pressure-test each against the hard rules. Kill anything that smells like AI.
4. Present them numbered, with the style label, ready to copy.

## Growing the example library

The engine's voice comes from `examples/replies.jsonl` (one JSON object per line:
`{"post": "...", "reply": "...", "style": "..."}`). When the user loves a reply —
theirs or one they saw in the wild — append it there. The library is the moat:
more good examples → better engine output. Keep examples short, real, and on-style;
remove anything that reads as generic.

## Manual drafting from the CLI

For a one-off without the skill, the engine is also reachable directly:

```
xgrowth draft "the tweet text here" --from somehandle
```

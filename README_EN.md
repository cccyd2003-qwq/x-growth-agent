<div align="center">

<img src="docs/logo.png" alt="xgrowth" width="96" height="96">

# HypeX

**go from 0 → 1 on X: Be first to every post.**

An open-source X (Twitter) growth agent. Point it at a watchlist, and when someone
posts, your *own* local Claude Code / Codex drafts 2–3 short, witty replies — then
pings you on Telegram so you pick one and post it yourself.

[![License](https://img.shields.io/badge/License-MIT-ff69b4.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-ff69b4.svg)](https://www.python.org)
[![Notify](https://img.shields.io/badge/notify-Telegram-ff69b4.svg)](https://telegram.org)
[![BYO](https://img.shields.io/badge/keys-bring_your_own-ff69b4.svg)](#requirements-all-yours-to-provide)

[How it works](#how-it-works) · [Install](#install) · [Quickstart](#quickstart) · [Commands](#commands) · [Config](#configuration) · [Telegram](#telegram-setup-60-seconds) · [Roadmap](#roadmap)

**English | [简体中文](README.md)**

</div>

> **Open-source · bring-your-own-key.** The LLM thinking runs on *your* machine
> through the coding agent you already use. xgrowth never proxies your credentials,
> and never auto-posts on your behalf.

---

<div align="center">

<img src="docs/architecture.png" alt="how xgrowth runs" width="100%">

</div>

## How it works

The engine is the always-awake **scheduler**; your Claude Code / Codex is the
**brain** that gets woken up, thinks for a few seconds, and goes back to sleep.
You don't keep a chat window open.

**Highlights**

- 🗂 **Digest, not spam.** Each poll cycle arrives as *one* Telegram message listing
  every new post (with "N minutes ago"). Tap a post to drill into the full text and
  reply suggestions — like a merged-forward card.
- 💬 **Conversational revise.** Reply to any draft with an instruction (`punchier`,
  `shorter`, `make it a meme`) and the brain re-drafts on the spot.
- ✂️ **Punchy by default.** Replies are capped at ~20 words (usually 10–15) — the
  length that actually lands on X.
- ⏰ **Time-windowed polling.** Only polls inside a daily window (default Beijing
  12:00–02:00, every 2h) so you don't burn API quota overnight.
- 🐦 **One call per cycle.** With the RapidAPI provider, the whole watchlist is polled
  in a single API call (each account's latest tweet comes back inline).

## Requirements (all yours to provide)

| Need | Where |
| --- | --- |
| **Twitter data** — a RapidAPI key (default, cheap) *or* official X API v2 bearer | [rapidapi.com](https://rapidapi.com) (e.g. *twitter241*) · [developer.x.com](https://developer.x.com) |
| **Claude Code** *or* **Codex** CLI installed | the "brain" (default model: Opus 4.8) |
| **Telegram bot token** | message [@BotFather](https://t.me/BotFather), `/newbot` |
| Python 3.10+ | |

> **Twitter provider.** Default is `rapidapi` — subscribe to a Twitter API on
> RapidAPI, copy the `x-rapidapi-key`, and the whole watchlist is polled in a
> *single* call per cycle. Set `twitter.provider: official` to use the official
> X API v2 instead.

## Install

```bash
git clone https://github.com/cccyd2003-qwq/x-growth-agent
cd x-growth-agent
pip install -e .
```

## Quickstart

```bash
xgrowth init                       # create ~/.xgrowth/config.yaml + db
# edit ~/.xgrowth/config.yaml: add twitter.rapidapi_key and notify.telegram.bot_token

xgrowth test-notify                # confirms Telegram, auto-detects your chat_id
xgrowth add naval                  # watch an account
xgrowth import-following yourhandle --min-followers 10000   # or bulk-pick from who you follow
xgrowth doctor                     # sanity-check everything

xgrowth start                      # run the agent (poll loop + Telegram + local panel)
```

Open the local panel at **http://127.0.0.1:7777** to manage the watchlist and
review recent drafts in a browser.

### Try a draft right now (no polling)

```bash
xgrowth draft "the most important skill of the next decade is learning to learn" --from naval
```

## Commands

| Command | Does |
| --- | --- |
| `xgrowth init` | Create config + database |
| `xgrowth add <handle>` | Add an account to the watchlist |
| `xgrowth rm <handle>` | Remove an account |
| `xgrowth list` | Show the watchlist |
| `xgrowth import-following <handle>` | Pull who you follow, pick a subset to watch |
| `xgrowth once` | Run one poll cycle and exit (good for cron) |
| `xgrowth start` | Run the full agent (loop + Telegram listener + panel) |
| `xgrowth panel` | Run only the local web panel |
| `xgrowth draft "<text>"` | Draft replies for a pasted tweet |
| `xgrowth test-notify` | Send a test notification |
| `xgrowth doctor` | Check config / keys / engine / notifier |

## Configuration

Lives at `~/.xgrowth/config.yaml` (override the dir with `XGROWTH_HOME`). See
[`config.example.yaml`](config.example.yaml) for every option. Highlights:

- `engine.provider` — `claude` or `codex`; `engine.model` — default `claude-opus-4-8`
- `engine.styles` — the reply styles to rotate (`神补刀`, `反直觉`, …)
- `poll.interval_minutes` — default 120; `poll.active_start_hour` / `active_end_hour` /
  `timezone_offset` — the daily polling window (default Beijing 12:00–02:00)
- `notify.provider` — `telegram` (full: digest + drill-in + conversational revise),
  `lark` / `bark` (stubs)

Secrets can also come from env vars: `XGROWTH_RAPIDAPI_KEY`, `XGROWTH_TELEGRAM_TOKEN`,
`XGROWTH_TELEGRAM_CHAT`.

## Telegram setup (60 seconds)

1. In Telegram, open **@BotFather**, send `/newbot`, follow the prompts, copy the **token**.
2. Put it in `notify.telegram.bot_token`.
3. Send any message to your new bot.
4. Run `xgrowth test-notify` — it finds and saves your `chat_id` automatically.

Each poll cycle sends **one digest message** listing every new post. Tap a post to
open its full text + reply drafts, with native **copy buttons**, a **🔄 regenerate**
button, and a link to the original. Don't like a draft? Just **reply to it** with an
instruction and the brain rewrites it.

## Skills (for Claude Code / Codex)

Two skills in [`skills/`](skills/) make the agent conversational inside your coding agent:

- **reply-craft** — co-write and sharpen replies by hand; grow the example library.
- **watchlist** — import your following list and curate who to watch.

The reply voice is defined once in `xgrowth/prompts.py` and seeded by
[`examples/replies.jsonl`](examples/replies.jsonl) — add your favorite real replies
there to make the engine sharper over time.

## Troubleshooting

- **`claude exited 1: ... model may not exist or you may not have access`** — your
  Claude Code default model isn't available in headless (`-p`) mode. Pin a known-good
  one in config: `engine.model: claude-haiku-4-5` or a Sonnet/Opus id you have access to.
- **Garbled output on Windows** — handled automatically; xgrowth forces UTF-8 stdout.
- **`/following` errors on `import-following`** — some API tiers gate that endpoint;
  add accounts manually with `xgrowth add` instead.

## Roadmap

- **MVP (this repo):** CLI engine (claude + codex) · reply-craft & watchlist skills ·
  Telegram digest + drill-in + conversational revise · local panel · time-windowed polling.
- **Next:** richer panel, full 飞书/Bark notifiers, reply analytics, cloud deploy guide.
- **Closed-source paid tier (separate):** hosted 24/7 cloud scheduling, web dashboard, managed keys.

## Design notes

See [`docs/PRODUCT.md`](docs/PRODUCT.md) for the full product rationale, the
open-source vs. paid split, and the architecture decisions behind this layout.

## License

MIT.

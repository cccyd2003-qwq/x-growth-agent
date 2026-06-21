# xgrowth — X (Twitter) 0-to-1 growth agent

Poll a watchlist of X accounts, and when one posts, have **your own local Claude
Code / Codex** draft 2–3 witty, scroll-stopping reply candidates — then get pinged
on **Telegram** so you pick one and post it yourself.

Built for going from **0 to 1** on X: the fastest organic growth is replying to
bigger accounts with something people actually notice.

> **Open-source · bring-your-own-key.** The LLM thinking runs on *your* machine
> through the coding agent you already use. xgrowth never proxies your credentials,
> and never auto-posts on your behalf.

---

## How it works

```
  ┌─ your local Claude Code / Codex ─┐   the "brain" (your login, your model)
  │   drafts the witty replies        │
  └───────────────▲──────────────────┘
                  │ headless: claude -p / codex exec
  ┌───────────────┴──────────────────┐
  │  xgrowth engine (always awake)    │   polls the whole watchlist in 1 call/cycle,
  │  poll → draft → digest → notify   │   on a daily time window you set
  └───────────────┬──────────────────┘
                  │
            ┌─────▼─────┐  one digest per cycle: a list of every new post,
            │ your phone │  tap a post → full text + drafts + [📋 copy] [🔄 regen] [🔗 original]
            └───────────┘  not happy? reply to the bot ("punchier" / "shorter") → re-drafted
```

The engine is the always-awake **scheduler**; your Claude Code / Codex is the
**brain** that gets woken up, thinks for a few seconds, and goes back to sleep.
You don't keep a chat window open.

Full run flow: [`docs/architecture.png`](docs/architecture.png).

**Highlights**

- **Digest, not spam.** Each poll cycle arrives as *one* Telegram message listing
  every new post (with "N minutes ago"). Tap a post to drill into the full text and
  reply suggestions — like a merged-forward card.
- **Conversational revise.** Reply to any draft message with an instruction
  (`更毒一点`, `shorter`, `make it a meme`) and the brain re-drafts on the spot.
- **Punchy by default.** Replies are capped at ~20 words (usually 10–15) — the
  length that actually lands on X.
- **Time-windowed polling.** Only polls inside a daily window (default Beijing
  12:00–02:00, every 2h) so you don't burn API quota overnight.

## Requirements (all yours to provide)

| Need | Where |
| --- | --- |
| **Twitter data** — a RapidAPI key (default, cheap) *or* official X API v2 bearer | https://rapidapi.com (e.g. *twitter241*) · https://developer.x.com |
| **Claude Code** *or* **Codex** CLI installed | the "brain" (default model: Opus 4.8) |
| **Telegram bot token** | message [@BotFather](https://t.me/BotFather), `/newbot` |
| Python 3.10+ | |

> **Twitter provider.** Default is `rapidapi` — subscribe to a Twitter API on
> RapidAPI, copy the `x-rapidapi-key`, and the whole watchlist is polled in a
> *single* call per cycle (each user's latest tweet comes back inline). Set
> `twitter.provider: official` to use the official X API v2 instead.

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

Secrets can also come from env vars: `XGROWTH_TWITTER_BEARER`,
`XGROWTH_TELEGRAM_TOKEN`, `XGROWTH_TELEGRAM_CHAT`.

## Telegram setup (60 seconds)

1. In Telegram, open **@BotFather**, send `/newbot`, follow the prompts, copy the **token**.
2. Put it in `notify.telegram.bot_token`.
3. Send any message to your new bot.
4. Run `xgrowth test-notify` — it finds and saves your `chat_id` automatically.

The reply card uses native Telegram **copy buttons** (tap to copy a draft to your
clipboard) and a **🔄 换一批** button that asks the brain for a fresh set.

## Skills (for Claude Code / Codex)

Two skills in [`skills/`](skills/) make the agent conversational inside your coding agent:

- **reply-craft** — co-write and sharpen replies by hand; grow the example library.
- **watchlist** — import your following list and curate who to watch.

The reply voice is defined once in `xgrowth/prompts.py` and seeded by
[`examples/replies.jsonl`](examples/replies.jsonl) — add your favorite real replies
there to make the engine sharper over time.

## Roadmap

- **MVP (this repo):** CLI engine (claude + codex) · reply-craft & watchlist skills · Telegram · local panel.
- **Next:** richer panel, more notifiers (full 飞书/Bark), reply analytics.
- **Closed-source paid tier (separate):** hosted 24/7 cloud scheduling, web dashboard, managed keys.

## Troubleshooting

- **`claude exited 1: ... model (claude-...) may not exist or you may not have access`** —
  your Claude Code default model isn't available in headless (`-p`) mode. Pin a
  known-good one in config: `engine.model: claude-haiku-4-5` (fast/cheap) or a
  Sonnet/Opus id you have access to.
- **`✗ ✓ ... gbk codec` / garbled output on Windows** — handled automatically;
  xgrowth forces UTF-8 stdout. If you still see issues, run in Windows Terminal.
- **`/following endpoint` errors on `import-following`** — some X API tiers require
  elevated access for that endpoint. Add accounts manually with `xgrowth add` instead.

## Design notes

See [`docs/PRODUCT.md`](docs/PRODUCT.md) for the full product rationale, the
open-source vs. paid split, and the architecture decisions behind this layout.

## License

MIT.

---
name: watchlist
description: Manage which X (Twitter) accounts the xgrowth agent monitors. Use when the user wants to import their following list and pick who to watch, add/remove accounts, or review and tune the watchlist conversationally.
---

# watchlist

Help the user decide *who* the xgrowth agent should watch, and keep that list sharp.
Watching the wrong accounts (too quiet, too off-topic, too huge to ever get noticed)
wastes API budget and buries good reply opportunities.

## Mental model

- The **watchlist** is the set of accounts the engine polls for new posts.
- It lives in the local SQLite DB (`~/.xgrowth/xgrowth.db`), managed via the
  `xgrowth` CLI. This skill drives that CLI conversationally.
- **Following ≠ watchlist.** A user may follow 500 accounts but only want to reply
  under ~20 high-signal ones. Curate hard.

## Core commands

```
xgrowth add <handle>            # resolve @handle -> id, start watching
xgrowth rm <handle>             # stop watching
xgrowth list                    # show current watchlist (followers, last seen)
xgrowth import-following <me>   # pull everyone <me> follows, then pick a subset
```

`import-following` flags:
- `--all` — watch everyone (rarely what you want)
- `--min-followers N` — only surface accounts above N followers
- `--limit N` — cap the list length

## Workflow: import + curate

1. Run `xgrowth import-following <their_handle> --min-followers 5000`.
2. Read the table back to the user. Help them choose by asking:
   - **Relevance** — is this account in the niche they want to grow in?
   - **Activity** — does it post often enough to create reply chances?
   - **Reachability** — replies under a 50M-follower account drown; mid-size
     accounts (10k–1M) with engaged audiences are often the sweet spot for 0-to-1.
3. Apply the selection (the command supports ranges like `1,3,5-8`).
4. Confirm with `xgrowth list`.

## Good defaults to suggest

- Start with **10–25 accounts**, not 200. Quality of reply opportunities > quantity.
- Favor accounts whose audience overlaps the niche the user wants to be known in.
- Drop anything that hasn't posted in weeks, or whose replies are a firehose nobody reads.
- Revisit monthly: prune the quiet ones, add new rising accounts.

## After curating

Remind the user the engine only acts on **enabled** accounts and only on **new**
posts after they're added. To start the agent: `xgrowth start`.

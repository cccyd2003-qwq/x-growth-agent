"""FastAPI local panel.

Zero-server, runs on localhost alongside the engine. Lets you manage the
watchlist and review recent draft candidates from a browser — the things that
are awkward to do over Telegram.
"""

from __future__ import annotations

import html
from typing import Optional

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from ..models import Post
from ..orchestrator import Orchestrator
from ..store import Store

CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", system-ui, sans-serif; margin: 0;
       background: #0f1419; color: #e7e9ea; }
.wrap { max-width: 880px; margin: 0 auto; padding: 24px; }
h1 { font-size: 20px; } h2 { font-size: 15px; color: #71767b; margin-top: 32px;
     text-transform: uppercase; letter-spacing: .5px; }
a { color: #1d9bf0; text-decoration: none; }
.card { background: #16202a; border: 1px solid #273340; border-radius: 14px;
        padding: 14px 16px; margin: 12px 0; }
.row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.muted { color: #71767b; font-size: 13px; }
.handle { font-weight: 600; color: #e7e9ea; }
.tweet { color: #c9cdd1; margin: 6px 0 10px; }
.cand { background: #1c2630; border-radius: 10px; padding: 8px 12px; margin: 6px 0; }
.style { color: #1d9bf0; font-size: 12px; font-weight: 600; }
input[type=text] { background: #0f1419; border: 1px solid #38444d; color: #e7e9ea;
        border-radius: 999px; padding: 8px 14px; outline: none; }
button { background: #1d9bf0; color: #fff; border: 0; border-radius: 999px;
        padding: 8px 16px; font-weight: 600; cursor: pointer; }
button.ghost { background: transparent; border: 1px solid #38444d; color: #e7e9ea; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #00ba7c; display: inline-block; }
"""


def _esc(s: str) -> str:
    return html.escape(s or "")


def build_app(cfg: dict, store: Store, orch: Orchestrator) -> FastAPI:
    app = FastAPI(title="xgrowth panel")

    def render() -> str:
        watch = store.list_watch()
        recents = store.recent_candidates(limit=15)

        watch_html = ""
        for e in watch:
            state = "✓" if e.enabled else "—"
            watch_html += f"""
            <div class="card row">
              <span class="dot"></span>
              <span class="handle">@{_esc(e.username)}</span>
              <span class="muted">{e.followers:,} followers · {state}</span>
              <form method="post" action="/remove" style="margin-left:auto">
                <input type="hidden" name="username" value="{_esc(e.username)}">
                <button class="ghost" type="submit">remove</button>
              </form>
            </div>"""
        if not watch:
            watch_html = '<p class="muted">No accounts yet. Add one above.</p>'

        rec_html = ""
        for r in recents:
            cands = "".join(
                f'<div class="cand"><div class="style">{_esc(c.style)}</div>{_esc(c.text)}</div>'
                for c in r["candidates"]
            )
            rec_html += f"""
            <div class="card">
              <div class="row">
                <span class="handle">@{_esc(r['username'])}</span>
                <a class="muted" href="https://x.com/{_esc(r['username'])}/status/{_esc(r['tweet_id'])}" target="_blank">original ↗</a>
                <form method="post" action="/regen" style="margin-left:auto">
                  <input type="hidden" name="tweet_id" value="{_esc(r['tweet_id'])}">
                  <button class="ghost" type="submit">🔄 regenerate</button>
                </form>
              </div>
              <div class="tweet">{_esc(r['tweet_text'])}</div>
              {cands}
            </div>"""
        if not recents:
            rec_html = '<p class="muted">No drafts yet. The engine fills this as new posts arrive.</p>'

        engine = cfg.get("engine", {}).get("provider", "?")
        notify = cfg.get("notify", {}).get("provider", "?")
        interval = cfg.get("poll", {}).get("interval_minutes", "?")

        return f"""<!doctype html><html><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>xgrowth</title><style>{CSS}</style></head><body><div class="wrap">
        <h1>🐦 xgrowth <span class="muted">· brain: {engine} · notify: {notify} · every {interval} min</span></h1>

        <h2>Add account</h2>
        <form method="post" action="/add" class="row">
          <input type="text" name="username" placeholder="@handle" autocomplete="off">
          <button type="submit">watch</button>
        </form>

        <h2>Watchlist ({len(watch)})</h2>
        {watch_html}

        <h2>Recent drafts</h2>
        {rec_html}
        </div></body></html>"""

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return render()

    @app.post("/add")
    def add(username: str = Form(...)) -> RedirectResponse:
        try:
            from ..twitter import build_twitter

            with build_twitter(cfg) as tw:
                u = tw.get_user(username)
            store.add_watch(u.id, u.username, u.followers)
        except Exception:
            pass  # panel stays forgiving; doctor/CLI surface real errors
        return RedirectResponse("/", status_code=303)

    @app.post("/remove")
    def remove(username: str = Form(...)) -> RedirectResponse:
        store.remove_watch(username)
        return RedirectResponse("/", status_code=303)

    @app.post("/regen")
    def regen(tweet_id: str = Form(...)) -> RedirectResponse:
        try:
            orch.regenerate(tweet_id)
        except Exception:
            pass
        return RedirectResponse("/", status_code=303)

    @app.get("/api/state")
    def api_state() -> dict:
        return {
            "watchlist": [
                {"username": e.username, "followers": e.followers, "enabled": e.enabled}
                for e in store.list_watch()
            ],
            "recent": [
                {
                    "username": r["username"],
                    "tweet_id": r["tweet_id"],
                    "tweet_text": r["tweet_text"],
                    "candidates": [c.to_dict() for c in r["candidates"]],
                }
                for r in store.recent_candidates(limit=15)
            ],
        }

    return app


def run_panel(cfg: dict, store: Store, orch: Orchestrator, host: str, port: int) -> None:
    import uvicorn

    app = build_app(cfg, store, orch)
    uvicorn.run(app, host=host, port=port, log_level="warning")

"""xgrowth command-line interface."""

from __future__ import annotations

import logging
import sys
from typing import Optional

# Windows consoles (esp. zh-CN, code page 936/GBK) can't encode ✓/emoji and would
# crash rich with UnicodeEncodeError. Force UTF-8 with a safe fallback before any
# output happens.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

import typer
from rich.console import Console
from rich.table import Table

from . import __version__, config as cfgmod
from .engines import build_engine
from .models import Post
from .notifiers import build_notifier
from .orchestrator import Orchestrator
from .store import Store

app = typer.Typer(
    add_completion=False,
    help="X (Twitter) 0-to-1 growth agent — poll accounts, draft witty replies, ping Telegram.",
)
console = Console()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _twitter(cfg: dict):
    from .twitter import build_twitter

    return build_twitter(cfg)


def _twitter_configured(cfg: dict) -> bool:
    tc = cfg.get("twitter", {})
    provider = (tc.get("provider") or "rapidapi").lower()
    if provider == "rapidapi":
        return bool(tc.get("rapidapi_key"))
    return bool(tc.get("bearer_token"))


def _build(cfg: dict) -> tuple[Store, Orchestrator]:
    store = Store()
    engine = build_engine(cfg)
    notifier = build_notifier(cfg)
    return store, Orchestrator(cfg, store, engine, notifier)


# ---------------------------------------------------------------------------
@app.command()
def version() -> None:
    """Print version."""
    console.print(f"xgrowth {__version__}")


@app.command()
def init(force: bool = typer.Option(False, "--force", help="Overwrite an existing config.")) -> None:
    """Create ~/.xgrowth/config.yaml and the local database."""
    cfgmod.ensure_home()
    path = cfgmod.write_default_config(force=force)
    Store()  # creates the db
    console.print(f"[green]✓[/] config: [cyan]{path}[/]")
    console.print(f"[green]✓[/] data dir: [cyan]{cfgmod.home_dir()}[/]")
    console.print(
        "\nNext:\n"
        "  1. Put your X API bearer token + Telegram bot token in the config.\n"
        "  2. [cyan]xgrowth add <username>[/] to watch an account.\n"
        "  3. [cyan]xgrowth test-notify[/] to check Telegram.\n"
        "  4. [cyan]xgrowth start[/] to run the agent."
    )


@app.command()
def add(username: str, verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """Add an X account to the watchlist (resolves @handle -> id)."""
    _setup_logging(verbose)
    cfg = cfgmod.load_config()
    store = Store()
    try:
        with _twitter(cfg) as tw:
            user = tw.get_user(username)
    except Exception as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1)
    store.add_watch(user.id, user.username, user.followers)
    console.print(f"[green]✓[/] watching [bold]@{user.username}[/] ({user.followers:,} followers)")


@app.command("rm")
def remove(username: str) -> None:
    """Remove an account from the watchlist."""
    store = Store()
    ok = store.remove_watch(username)
    if ok:
        console.print(f"[green]✓[/] removed @{username.lstrip('@')}")
    else:
        console.print(f"[yellow]·[/] @{username.lstrip('@')} was not in the watchlist")


@app.command("list")
def list_watch() -> None:
    """Show the watchlist."""
    store = Store()
    entries = store.list_watch()
    if not entries:
        console.print("[yellow]watchlist is empty.[/] add one with `xgrowth add <username>`")
        return
    table = Table(title="watchlist")
    table.add_column("@handle", style="cyan")
    table.add_column("followers", justify="right")
    table.add_column("enabled", justify="center")
    table.add_column("last seen tweet")
    for e in entries:
        table.add_row(
            f"@{e.username}",
            f"{e.followers:,}",
            "✓" if e.enabled else "—",
            e.last_seen_tweet_id or "—",
        )
    console.print(table)


@app.command("import-following")
def import_following(
    username: str,
    all_: bool = typer.Option(False, "--all", help="Import every followed account, no prompt."),
    min_followers: int = typer.Option(0, "--min-followers", help="Only show accounts above N followers."),
    limit: int = typer.Option(0, "--limit", help="Cap how many to list (0 = no cap)."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Pull who @username follows, then pick which ones to watch."""
    _setup_logging(verbose)
    cfg = cfgmod.load_config()
    store = Store()
    try:
        with _twitter(cfg) as tw:
            me = tw.get_user(username)
            console.print(f"fetching accounts @{me.username} follows…")
            following = tw.get_following(me.id)
    except Exception as e:
        console.print(f"[red]✗[/] {e}")
        console.print(
            "[dim]note: the /following endpoint may need elevated API access on some tiers.[/]"
        )
        raise typer.Exit(1)

    following = [u for u in following if u.followers >= min_followers]
    following.sort(key=lambda u: u.followers, reverse=True)
    if limit:
        following = following[:limit]

    if not following:
        console.print("[yellow]no accounts matched.[/]")
        return

    table = Table(title=f"@{me.username} follows ({len(following)})")
    table.add_column("#", justify="right", style="dim")
    table.add_column("@handle", style="cyan")
    table.add_column("name")
    table.add_column("followers", justify="right")
    for i, u in enumerate(following, 1):
        table.add_row(str(i), f"@{u.username}", u.name, f"{u.followers:,}")
    console.print(table)

    if all_:
        chosen = following
    else:
        raw = typer.prompt(
            "watch which? (e.g. 1,3,5-8 / 'all' / blank to cancel)", default="", show_default=False
        )
        chosen = _select(following, raw)
    if not chosen:
        console.print("[yellow]nothing selected.[/]")
        return
    for u in chosen:
        store.add_watch(u.id, u.username, u.followers)
    console.print(f"[green]✓[/] added {len(chosen)} account(s) to the watchlist.")


def _select(items: list, spec: str) -> list:
    spec = (spec or "").strip().lower()
    if not spec:
        return []
    if spec == "all":
        return list(items)
    picked: set[int] = set()
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                for n in range(int(a), int(b) + 1):
                    picked.add(n)
            except ValueError:
                continue
        else:
            try:
                picked.add(int(part))
            except ValueError:
                continue
    return [items[i - 1] for i in sorted(picked) if 1 <= i <= len(items)]


@app.command()
def once(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """Run a single poll cycle and exit (handy for cron)."""
    _setup_logging(verbose)
    cfg = cfgmod.load_config()
    from .poller import run_once

    store, orch = _build(cfg)
    with _twitter(cfg) as tw:
        n = run_once(cfg, store, tw, orch)
    console.print(f"[green]✓[/] cycle done — {n} new post(s) handled.")


@app.command()
def start(
    no_panel: bool = typer.Option(False, "--no-panel", help="Don't launch the local web panel."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the agent: poll loop + Telegram listener + (optional) local panel."""
    _setup_logging(verbose)
    cfg = cfgmod.load_config()
    store, orch = _build(cfg)

    if not _twitter_configured(cfg):
        console.print("[red]✗[/] twitter provider not configured. run `xgrowth init` then add your key.")
        raise typer.Exit(1)

    panel_cfg = cfg.get("panel", {})
    if panel_cfg.get("enabled", True) and not no_panel:
        _start_panel_thread(cfg, store, orch)

    console.print("[green]▶[/] xgrowth running. Ctrl-C to stop.")
    from .poller import run_loop

    try:
        with _twitter(cfg) as tw:
            run_loop(cfg, store, tw, orch)
    except KeyboardInterrupt:
        console.print("\n[yellow]stopped.[/]")


def _start_panel_thread(cfg: dict, store: Store, orch: Orchestrator) -> None:
    import threading

    from .panel.app import run_panel

    host = cfg["panel"].get("host", "127.0.0.1")
    port = int(cfg["panel"].get("port", 7777))
    t = threading.Thread(
        target=run_panel, args=(cfg, store, orch, host, port), daemon=True, name="panel"
    )
    t.start()
    console.print(f"[green]◐[/] panel: [cyan]http://{host}:{port}[/]")


@app.command()
def panel(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """Run only the local web panel (no polling)."""
    _setup_logging(verbose)
    cfg = cfgmod.load_config()
    store, orch = _build(cfg)
    from .panel.app import run_panel

    host = cfg["panel"].get("host", "127.0.0.1")
    port = int(cfg["panel"].get("port", 7777))
    console.print(f"[green]◐[/] panel at [cyan]http://{host}:{port}[/]  (Ctrl-C to stop)")
    run_panel(cfg, store, orch, host, port)


@app.command("test-notify")
def test_notify() -> None:
    """Send a test message through the configured notifier."""
    cfg = cfgmod.load_config()
    notifier = build_notifier(cfg)
    provider = cfg["notify"]["provider"]

    if provider == "telegram" and not cfg["notify"]["telegram"].get("chat_id"):
        # Help the user discover their chat id.
        from .notifiers.telegram import TelegramNotifier

        tg: TelegramNotifier = notifier  # type: ignore
        if not tg.bot_token:
            console.print("[red]✗[/] set notify.telegram.bot_token first (from @BotFather).")
            raise typer.Exit(1)
        console.print(
            "[yellow]no chat_id set.[/] Open Telegram, send any message to your bot, then re-run."
        )
        chat = tg.discover_chat_id()
        if chat:
            cfg["notify"]["telegram"]["chat_id"] = chat
            cfgmod.save_config(cfg)
            console.print(f"[green]✓[/] found and saved chat_id = [cyan]{chat}[/]")
            notifier = build_notifier(cfg)
        else:
            console.print("[red]✗[/] couldn't find a chat. Did you message the bot?")
            raise typer.Exit(1)

    if not notifier.configured():
        console.print(f"[red]✗[/] notifier '{provider}' is not fully configured. check config.yaml")
        raise typer.Exit(1)
    try:
        notifier.send_text("✅ xgrowth test — notifications are working.")
    except Exception as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1)
    console.print(f"[green]✓[/] sent a test message via {provider}. check your phone.")


@app.command()
def draft(
    text: str = typer.Argument(..., help="The tweet text to reply to (in quotes)."),
    username: str = typer.Option("someone", "--from", help="The author handle."),
    notify: bool = typer.Option(False, "--notify", help="Also push to your notifier."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Draft replies for a pasted tweet, right now (no polling)."""
    _setup_logging(verbose)
    cfg = cfgmod.load_config()
    store, orch = _build(cfg)
    post = Post(tweet_id="manual-0", username=username.lstrip("@"), author_id="", text=text)
    try:
        candidates = orch.handle_post(post, notify=notify)
    except Exception as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1)
    console.print(f"\n[bold]@{post.username}:[/] {text}\n")
    for i, c in enumerate(candidates, 1):
        console.print(f"[cyan]{i}. [{c.style}][/] {c.text}")


@app.command()
def doctor() -> None:
    """Check the environment: config, keys, engine, notifier."""
    import shutil

    cfg = cfgmod.load_config()
    rows = []

    rows.append(("config file", "✓" if cfgmod.config_exists() else "✗ run `xgrowth init`"))
    tprov = cfg["twitter"].get("provider", "rapidapi")
    rows.append((f"twitter ({tprov})", "✓" if _twitter_configured(cfg) else "✗ missing key"))

    provider = cfg["engine"]["provider"]
    path = cfg["engine"].get(f"{provider}_path", provider)
    rows.append((f"engine ({provider})", "✓" if shutil.which(path) else f"✗ `{path}` not on PATH"))

    nprov = cfg["notify"]["provider"]
    notifier = build_notifier(cfg)
    rows.append((f"notifier ({nprov})", "✓" if notifier.configured() else "✗ not configured"))

    n_watch = len(Store().list_watch())
    rows.append(("watchlist", f"{n_watch} account(s)"))

    table = Table(title="xgrowth doctor")
    table.add_column("check", style="cyan")
    table.add_column("status")
    for k, v in rows:
        table.add_row(k, v)
    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()

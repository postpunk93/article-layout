# cli.py
"""Unified entry point for the article-layout adapters.

  python cli.py login  <client> <platform>
  python cli.py status [client]
  python cli.py layout <slug> <client> <platforms>   # platforms: vc,pikabu | all

`login` is interactive (run it yourself: `! python cli.py login acme pikabu`).
`layout` checks every requested session first; if any is dead it lays out
NOTHING and tells you who to log in.
"""
import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from src import sessions, orchestrator
from src.parser import parse


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def cmd_login(args):
    platform = args.platform
    if platform not in sessions.PLATFORMS:
        print(f"Unknown platform {platform!r}; known: {', '.join(sessions.known_platforms())}")
        return 2
    entry = sessions.PLATFORMS[platform]
    if entry.get("manual_login"):
        # Login captcha blanks under CDP — launch a plain Chrome (no automation).
        url = entry.get("login_url", entry["editor_url"])
        proc = sessions.manual_login(args.client, platform, url)
        print(f"Chrome open for {args.client}/{platform}. Log in, then come back here.")
        try:
            input("Press Enter once you're logged in to save the session...")
        except EOFError:
            time.sleep(120)
        proc.terminate()
    else:
        with sync_playwright() as p:
            ctx, page = sessions.open_context(p, args.client, platform, headless=False)
            page.goto(entry["editor_url"], wait_until="domcontentloaded")
            print(f"Browser open for {args.client}/{platform}. Log in, then come back here.")
            try:
                input("Press Enter once you're logged in to save the session...")
            except EOFError:
                time.sleep(120)
            ctx.close()
    sessions.write_meta(args.client, platform, {"last_login_at": _today()})
    print(f"Saved session for {args.client}/{platform}.")
    return 0


def cmd_status(args):
    clients = [args.client] if args.client else sessions.list_clients()
    if not clients:
        print("No profiles yet. Use: python cli.py login <client> <platform>")
        return 0
    print(f"{'client':<16}{'platform':<10}{'state':<8}label")
    for client in clients:
        for platform in sessions.list_accounts(client):
            state = "alive" if sessions.is_alive(client, platform) else "DEAD"
            label = sessions.read_meta(client, platform).get("label", "")
            print(f"{client:<16}{platform:<10}{state:<8}{label}")
    return 0


def cmd_layout(args):
    try:
        platforms = orchestrator.parse_platforms(args.platforms, sessions.known_platforms())
    except ValueError as e:
        print(str(e))
        return 2

    slug_dir = Path("in") / args.slug
    index = slug_dir / "index.html"
    if not index.exists():
        print(f"Not found: {index}")
        return 1
    doc = parse(index.read_text(encoding="utf-8"))
    images_dir = slug_dir / "images"
    print(f"Parsed: title={doc.title!r}, blocks={len(doc.blocks)}")

    print(f"Checking sessions for {args.client}: {', '.join(platforms)} ...")
    ok, dead = orchestrator.precheck(args.client, platforms, sessions.is_alive)
    if not ok:
        for client, platform in dead:
            print(f"DEAD: {client}/{platform} — run: python cli.py login {client} {platform}")
        print("Laid out nothing (all-or-nothing). Log in the dead sessions, then retry.")
        return 1

    failures = []
    for platform in platforms:
        entry = sessions.PLATFORMS[platform]
        print(f"--- {args.client}/{platform} ---")
        with sync_playwright() as p:
            ctx, page = sessions.open_context(p, args.client, platform, headless=False)
            try:
                entry["build_document"](page, doc, images_dir)
                print(f"Done — {platform} draft built. Review and publish manually.")
            except Exception as e:  # noqa: BLE001 — report and continue to next platform
                failures.append((platform, repr(e)))
                print(f"FAILED {platform}: {e!r} (window left open)")
            try:
                input(f"Press Enter to close {platform} browser...")
            except EOFError:
                time.sleep(15)
            ctx.close()

    if failures:
        print("Failures: " + ", ".join(f"{p}: {err}" for p, err in failures))
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(prog="cli.py")
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="open a browser to log in to a (client, platform)")
    p_login.add_argument("client")
    p_login.add_argument("platform")
    p_login.set_defaults(func=cmd_login)

    p_status = sub.add_parser("status", help="show alive/dead per session")
    p_status.add_argument("client", nargs="?")
    p_status.set_defaults(func=cmd_status)

    p_layout = sub.add_parser("layout", help="lay out in/<slug> for a client on platforms")
    p_layout.add_argument("slug")
    p_layout.add_argument("client")
    p_layout.add_argument("platforms", help="comma list (vc,pikabu) or 'all'")
    p_layout.set_defaults(func=cmd_layout)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()

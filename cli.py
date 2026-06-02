# cli.py
"""Unified entry point for the article-layout adapters.

  python cli.py login  <client>
  python cli.py status [client]
  python cli.py layout <slug> <client> <platforms>   # platforms: vc,pikabu,habr | all

`login` is interactive (run it yourself: `! python cli.py login acme`).
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
    # One plain Chrome on the client's shared profile, a tab per platform's login/editor
    # URL. Log into the ones you need, then press Enter. NEVER publishes anything.
    urls = []
    for platform in sessions.known_platforms():
        entry = sessions.PLATFORMS[platform]
        urls.append(entry.get("login_url", entry["editor_url"]))
    proc = sessions.manual_login(args.client, urls)
    print(f"Открыл окно Chrome для клиента «{args.client}»: по вкладке на каждую площадку. "
          f"Войдите в те площадки, что вам нужны, затем вернитесь сюда, в терминал.")
    try:
        input("Когда войдёте на нужные площадки, нажмите Enter здесь, чтобы сохранить сессию...")
    except EOFError:
        time.sleep(120)
    proc.terminate()
    sessions.write_meta(args.client, {"last_login_at": _today()})
    print(f"Сессия для клиента «{args.client}» сохранена.")
    return 0


def cmd_status(args):
    clients = [args.client] if args.client else sessions.list_clients()
    if not clients:
        print("Пока нет ни одного клиента. Создайте его командой: ! python cli.py login <клиент>")
        return 0
    platforms = sessions.known_platforms()
    markers = {p: sessions.PLATFORMS[p]["alive_marker"] for p in platforms}
    print(f"{'клиент':<16}{'площадка':<10}{'статус':<8}метка")
    with sync_playwright() as p:
        for client in clients:
            label = sessions.read_meta(client).get("label", "")
            ctx, first_page = sessions.open_context(p, client, headless=True)
            try:
                pages = {}
                for i, platform in enumerate(platforms):
                    page = first_page if i == 0 else ctx.new_page()
                    page.goto(sessions.PLATFORMS[platform]["editor_url"],
                              wait_until="domcontentloaded")
                    pages[platform] = page
                dead = orchestrator.check_alive(pages, markers)
            finally:
                ctx.close()
            for platform in platforms:
                state = "мёртв" if platform in dead else "жив"
                print(f"{client:<16}{platform:<10}{state:<8}{label}")
    return 0


def cmd_layout(args):
    """Build drafts for one client across platforms in a single browser window.

    NEVER publishes: builds drafts and leaves the window open for the human to
    review and publish manually. No publish action is ever taken here.
    """
    try:
        platforms = orchestrator.parse_platforms(args.platforms, sessions.known_platforms())
    except ValueError as e:
        print(str(e))
        return 2

    slug_dir = Path("in") / args.slug
    index = slug_dir / "index.html"
    if not index.exists():
        print(f"Статья не найдена: {index}. Проверьте, что файлы лежат в папке in/{args.slug}/ "
              f"(внутри должен быть index.html).")
        return 1
    doc = parse(index.read_text(encoding="utf-8"))
    images_dir = slug_dir / "images"
    print(f"Статья разобрана: заголовок={doc.title!r}, блоков={len(doc.blocks)}.")

    markers = {p: sessions.PLATFORMS[p]["alive_marker"] for p in platforms}
    failures = []
    with sync_playwright() as p:
        ctx, first_page = sessions.open_context(p, args.client, headless=False)

        # Liveness phase (all-or-nothing): one tab per platform, navigate, check marker.
        # Reuse the profile's initial tab for the first platform so no blank tab lingers.
        print(f"Проверяю сессии клиента «{args.client}»: {', '.join(platforms)} ...")
        pages = {}
        for i, platform in enumerate(platforms):
            page = first_page if i == 0 else ctx.new_page()
            try:
                page.goto(sessions.PLATFORMS[platform]["editor_url"],
                          wait_until="domcontentloaded")
            except Exception:  # noqa: BLE001 — unreachable editor falls through to a DEAD verdict
                pass
            pages[platform] = page
        dead = orchestrator.check_alive(pages, markers)
        if dead:
            for platform in dead:
                print(f"Сессия мертва: {args.client}/{platform}. Залогиньтесь заново командой: "
                      f"! python cli.py login {args.client}")
            print("Ничего не сверстал — действует правило «всё или ничего». "
                  "Войдите в нужные площадки и запустите снова.")
            ctx.close()
            return 1

        # Build phase: same tabs, sequential (real-clipboard paste can't run in parallel).
        contexts = [("window", ctx)]
        for platform in platforms:
            print(f"--- {args.client}/{platform} ---")
            try:
                sessions.PLATFORMS[platform]["build_document"](pages[platform], doc, images_dir)
                print(f"Готово — черновик на площадке {platform} собран. "
                      f"Проверьте и опубликуйте вручную.")
            except Exception as e:  # noqa: BLE001 — report and continue to next platform
                failures.append((platform, repr(e)))
                print(f"Ошибка на площадке {platform}: {e!r} (вкладка оставлена открытой).")

        print(
            f"\nВсе вкладки ({len(platforms)} шт.) открыты в одном окне. "
            "Проверьте черновики и опубликуйте вручную. Само ничего не закроется — "
            "закройте окно сами, когда закончите (выйти можно и через Ctrl+C)."
        )
        orchestrator.wait_until_all_closed(contexts, pump=lambda pg: pg.wait_for_timeout(500))

    if failures:
        print("Ошибки: " + ", ".join(f"{p}: {err}" for p, err in failures))
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(prog="cli.py")
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="open one Chrome to log in to all platforms for a client")
    p_login.add_argument("client")
    p_login.set_defaults(func=cmd_login)

    p_status = sub.add_parser("status", help="show alive/dead per session")
    p_status.add_argument("client", nargs="?")
    p_status.set_defaults(func=cmd_status)

    p_layout = sub.add_parser("layout", help="lay out in/<slug> for a client on platforms")
    p_layout.add_argument("slug")
    p_layout.add_argument("client")
    p_layout.add_argument("platforms", help="comma list (vc,pikabu,habr) or 'all'")
    p_layout.set_defaults(func=cmd_layout)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()

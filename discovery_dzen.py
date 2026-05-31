# discovery_dzen.py
"""Throwaway discovery harness for the Dzen article editor (NOT the adapter).

Two phases, because Dzen logs in via Yandex (SmartCaptcha blanks under CDP):

  python discovery_dzen.py login    # YOU run this (`! python ...`); log in by hand
  python discovery_dzen.py inspect  # reopens the saved profile under Playwright

`login` opens a plain non-CDP Chrome on .profiles/<client>/dzen, you log in to
Yandex/Dzen and navigate to the ARTICLE editor, then press Enter to save+close.
`inspect` reopens that same profile under Playwright (channel=chrome) and dumps
screenshots + HTML + candidate selectors to discovery/ for analysis.

Outputs land in discovery/ . Safe to delete the whole thing afterwards.
"""
import sys
import time
from pathlib import Path

from src import sessions

CLIENT = "default"
PLATFORM = "dzen"
CREATE_URL = "https://dzen.ru/profile/editor/create"
DEBUG_PORT = 9222
OUT = Path("discovery")


def phase_login():
    proc = sessions.manual_login(CLIENT, PLATFORM, CREATE_URL)
    print(f"Chrome open on .profiles/{CLIENT}/{PLATFORM}.")
    print("1) Log in to Yandex/Dzen.")
    print("2) Click the + in the navbar, choose 'Написать статью', land in the editor.")
    print("3) Leave it on the article editor, then come back here.")
    try:
        input("Press Enter once you're IN the article editor to save the session...")
    except EOFError:
        time.sleep(180)
    proc.terminate()
    sessions.write_meta(CLIENT, PLATFORM, {"last_login_at": time.strftime("%Y-%m-%d")})
    print(f"Saved session for {CLIENT}/{PLATFORM}.")


def _dump(page, tag):
    OUT.mkdir(exist_ok=True)
    page.screenshot(path=str(OUT / f"{tag}.png"), full_page=True)
    (OUT / f"{tag}.html").write_text(page.content(), encoding="utf-8")
    print(f"  wrote {tag}.png / {tag}.html  (url={page.url})")


def _clickables(page):
    """List buttons/links/role=menuitem with visible text — to find the + and menu."""
    return page.evaluate(
        """() => {
          const out = [];
          const sel = 'button, a, [role=button], [role=menuitem], [aria-label]';
          for (const el of document.querySelectorAll(sel)) {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            const txt = (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 40);
            out.push({tag: el.tagName, txt, cls: (el.className||'').toString().slice(0,60),
                      x: Math.round(r.x), y: Math.round(r.y)});
          }
          return out.slice(0, 120);
        }"""
    )


def phase_inspect():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx, page = sessions.open_context(p, CLIENT, PLATFORM, headless=False)
        try:
            page.goto(CREATE_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            _dump(page, "01-landing")

            print("Clickable elements on landing (look for + / 'Написать статью'):")
            for c in _clickables(page):
                print(f"  [{c['tag']}] '{c['txt']}' @({c['x']},{c['y']}) .{c['cls']}")

            print("\nLeaving the window open. Inspect manually if needed.")
            try:
                input("Press Enter to close the inspection browser...")
            except EOFError:
                page.wait_for_timeout(20000)
        finally:
            ctx.close()


def phase_serve():
    """Launch a REAL Chrome (no automation flags) with a CDP debug port and keep
    it alive. Yandex's anti-bot accepts this; a normally-closed manual login drops
    the session (master Yandex SSO cookie is session-scoped), so we never close —
    Playwright attaches to THIS process via `attach`.
    """
    import subprocess

    exe = sessions.chrome_executable()
    if not exe:
        raise RuntimeError("Chrome not found.")
    pdir = sessions.profile_dir(CLIENT, PLATFORM).resolve()
    pdir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([
        exe,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={pdir}",
        CREATE_URL,
    ])
    print(f"Real Chrome up on port {DEBUG_PORT}, profile {pdir}.")
    print("Log in, open the article editor, and LEAVE IT OPEN.")
    print("Then (in another terminal / via the agent) run: python discovery_dzen.py attach")
    print("This process keeps Chrome alive — close this window or Ctrl-C when done.")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


def _pick_editor_page(browser):
    """From the live Chrome, return the page that looks like the Dzen editor.

    Prefer a page already in the article editor (`/edit`); else any dzen page.
    """
    pages = [pg for ctx in browser.contexts for pg in ctx.pages]
    dzen = [pg for pg in pages if "dzen.ru" in pg.url and "passport" not in pg.url]
    for pg in dzen:
        if "/edit" in pg.url:
            return pg
    return dzen[0] if dzen else (pages[0] if pages else None)


def _open_editor(page, log=print):
    """Ensure `page` is in a fresh article editor; return True if BODY_SEL is present.

    In a LIVE logged-in session, /profile/editor/create should not bounce to passport.
    Tries: (a) already in /edit; (b) goto create and see if the editor opens directly;
    (c) click the navbar '+' then the 'Написать статью' menu item.
    """
    if "/edit" in page.url:
        try:
            page.wait_for_selector(BODY_SEL, timeout=5000)
            return True
        except Exception:
            pass
    page.goto(CREATE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    log(f"  after goto create: {page.url}")
    try:
        page.wait_for_selector(BODY_SEL, timeout=4000)
        return True
    except Exception:
        pass
    # The studio header "+" -> dropdown -> "Написать статью".
    plus = page.locator('[data-testid="add-publication-button"]')
    if plus.count():
        plus.first.click()
        page.wait_for_timeout(1000)
        for item in ['text=Написать статью', 'text=Статья', '[data-testid*="article"]']:
            loc = page.locator(item)
            if loc.count():
                loc.first.click()
                break
    page.wait_for_timeout(3000)
    log(f"  after +/Написать статью: {page.url}")
    try:
        page.wait_for_selector(BODY_SEL, timeout=4000)
        return True
    except Exception:
        return False


BODY_SEL = 'div.public-DraftEditor-content[aria-describedby="placeholder-ZenDraftEditor"]'
# 2x2 red PNG, to see whether Dzen ingests a pasted <img> (like Habr) or strips it (like VC).
_RED_PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAEklEQVR4n"
            "GP8z8Dwn4EIwDiqkL4KAcT9Cv8wWdAUAAAAAElFTkSuQmCC")
TEST_HTML = (
    "<h2>Тестовый подзаголовок H2</h2>"
    "<p>Обычный абзац с <strong>жирным</strong> и <em>курсивом</em> текстом.</p>"
    "<blockquote>Это цитата, которую надо опознать после вставки.</blockquote>"
    "<ul><li>первый пункт</li><li>второй пункт</li></ul>"
    f'<p><img src="{_RED_PNG}"></p>'
    "<p>Подпись под картинкой (конвенция GDoc).</p>"
)


def _set_clipboard(page, html):
    page.evaluate(
        """async (html) => {
            const plain = html.replace(/<[^>]+>/g, '');
            await navigator.clipboard.write([new ClipboardItem({
                'text/html': new Blob([html], {type: 'text/html'}),
                'text/plain': new Blob([plain], {type: 'text/plain'}),
            })]);
        }""",
        html,
    )


def phase_pastetest():
    """Paste a small representative snippet into the live editor and dump the result."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
        page = _pick_editor_page(browser)
        if page is None:
            print("No editor page found.")
            return
        try:
            page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception as e:
            print(f"(grant_permissions failed, trying anyway: {e})")
        page.bring_to_front()
        if not _open_editor(page):
            print(f"Could not reach the article editor. Current url: {page.url}")
            _dump(page, "19-no-editor")
            browser.close()
            return
        print(f"Pasting into: {page.url}")
        page.click(BODY_SEL)
        page.wait_for_timeout(300)
        _set_clipboard(page, TEST_HTML)
        page.keyboard.press("Control+V")
        page.wait_for_timeout(2500)
        _dump(page, "20-after-paste")
        # Structural report of the body's DraftJS blocks.
        report = page.evaluate(
            """(sel) => {
                const body = document.querySelector(sel);
                if (!body) return {error: 'no body'};
                const blocks = [...body.querySelectorAll('[data-block="true"]')].map(b => {
                    const inner = b.firstElementChild;
                    return {
                        tag: inner ? inner.tagName : b.tagName,
                        cls: (inner ? inner.className : b.className).toString().slice(0, 50),
                        text: (b.innerText || '').slice(0, 45),
                    };
                });
                return {
                    blockCount: blocks.length,
                    imgInBody: body.querySelectorAll('img').length,
                    figureInBody: body.querySelectorAll('figure').length,
                    blocks,
                };
            }""",
            BODY_SEL,
        )
        print("PASTE RESULT:")
        import json as _json
        print(_json.dumps(report, ensure_ascii=False, indent=2))
        browser.close()


def phase_attach():
    """Connect to the live Chrome over CDP and inspect the open editor — no close."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
        page = _pick_editor_page(browser)
        if page is None:
            print("No page found in the live Chrome.")
            return
        print(f"Attached. Active editor url = {page.url}")
        _dump(page, "10-editor")
        print("Clickable elements in editor:")
        for c in _clickables(page):
            print(f"  [{c['tag']}] '{c['txt']}' @({c['x']},{c['y']}) .{c['cls']}")
        # Leave Chrome alive; just detach Playwright.
        browser.close()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "login":
        phase_login()
    elif mode == "inspect":
        phase_inspect()
    elif mode == "serve":
        phase_serve()
    elif mode == "attach":
        phase_attach()
    elif mode == "pastetest":
        phase_pastetest()
    else:
        print(__doc__)
        sys.exit(2)

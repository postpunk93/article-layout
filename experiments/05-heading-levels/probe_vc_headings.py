"""Probe the VC (Editor.js) toolbox to find the H3 («Подзаголовок») control.

Usage: python -m experiments.05-heading-levels.probe_vc_headings
       (or: python experiments/05-heading-levels/probe_vc_headings.py)

GOAL: learn the exact selector/index that yields the "Подзаголовок H3" toolbox
item. vc_adapter._insert_heading currently clicks the FIRST
`.ce-toolbox__item[data-type="header"]` (which is H2). We expect the header
items to appear in order [0]=H2, [1]=H3 — but this MUST be confirmed by the dump
below before Task 4 relies on it.

What it does (reusing the existing discover/explore VC idioms exactly):
1. Launches a visible Chromium with the persistent profile `.vc-profile` (same as
   src/discover_vc.py and src/explore_vc.py).
2. Opens the editor at https://vc.ru/?modal=editor (same as src/explore_vc.py /
   src/vc_adapter.py) and types a title + a paragraph + an empty block so the
   add-block "+" becomes available (Editor.js shows the "+" on an EMPTY block).
3. Opens the toolbox by mirroring vc_adapter._open_toolbox: anchor the toolbar to
   the last block with a real click, click `.ce-toolbar__plus` (JS-click fallback),
   then wait for `.ce-popover.ce-toolbox.opened`.
4. Dumps EVERY `.ce-toolbox__item` in DOM order as
   {"data-type": <attr>, "text": <trimmed innerText>} to stdout (pretty JSON) and
   to experiments/05-heading-levels/vc_toolbox.json.
5. Keeps the browser open at the end for manual inspection.

This is a DISCOVERY probe — it requires an already-authenticated .vc-profile and
must be run by hand.
"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# Reuse the EXACT profile dir / URL / selectors from the real VC adapter & explorer.
PROFILE_DIR = ".vc-profile"
EDITOR_URL = "https://vc.ru/?modal=editor"
TITLE_SEL = 'div.editor-tool-input[data-placeholder="Заголовок"]'
TOOLBOX_OPEN_SEL = ".ce-popover.ce-toolbox.opened"
OUT = Path("experiments/05-heading-levels/vc_toolbox.json")

# Dump every toolbox item in DOM order as {data-type, text}.
_DUMP_TOOLBOX_JS = r"""
() => Array.from(document.querySelectorAll('.ce-toolbox__item')).map(el => ({
  'data-type': el.getAttribute('data-type'),
  'text': (el.innerText || '').trim(),
}))
"""


def _open_toolbox(page):
    # Mirror vc_adapter._open_toolbox: anchor the toolbar to the last block with a
    # REAL click, click the "+" (JS fallback), then wait for the toolbox popover.
    try:
        page.locator(".codex-editor .ce-block").last.click()
    except Exception:
        pass
    try:
        page.click(".ce-toolbar__plus", timeout=5000)
    except Exception:
        page.eval_on_selector(".ce-toolbar__plus", "el => el.click()")
    page.wait_for_selector(TOOLBOX_OPEN_SEL, timeout=5000)


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print(f"Opening {EDITOR_URL} ...", flush=True)
        page.goto(EDITOR_URL)
        page.wait_for_selector(TITLE_SEL, timeout=30000)
        time.sleep(2)

        # Title -> body paragraph -> empty block (so the "+" toolbox is available).
        print("Typing title + a paragraph + an empty block ...", flush=True)
        page.click(TITLE_SEL)
        page.keyboard.type("ТЕСТ: разведка уровней заголовков")
        page.keyboard.press("Enter")
        time.sleep(0.5)
        page.keyboard.type("Первый абзац тела для разведки заголовков.")
        page.keyboard.press("Enter")  # fresh empty block — "+" becomes visible
        time.sleep(1)

        print("Opening the '+' toolbox ...", flush=True)
        _open_toolbox(page)
        time.sleep(0.5)

        items = page.evaluate(_DUMP_TOOLBOX_JS)
        pretty = json.dumps(items, ensure_ascii=False, indent=2)
        print(pretty, flush=True)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(pretty, encoding="utf-8")
        print(f"\nWrote {len(items)} toolbox item(s) to {OUT}", flush=True)

        headers = [i for i in items if i["data-type"] == "header"]
        print(f"data-type=\"header\" items (in DOM order): {headers}", flush=True)

        print("Browser left open for inspection.", flush=True)
        try:
            input("Press Enter here to close the browser...")
        except EOFError:
            time.sleep(30)
        ctx.close()


if __name__ == "__main__":
    main()

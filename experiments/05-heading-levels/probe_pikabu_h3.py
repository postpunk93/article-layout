"""Probe whether Pikabu's Tiptap editor keeps <h3> as a distinct second level.

Usage: python -m experiments.05-heading-levels.probe_pikabu_h3
       (or: python experiments/05-heading-levels/probe_pikabu_h3.py)

GOAL: confirm whether `<h3>` survives a high-fidelity HTML paste as a SECOND,
distinct heading level («Заголовок 2») or is collapsed into <h2> / dropped. The
answer decides whether Task 4 needs a per-node fallback when emitting H3 to Pikabu.

What it does (reusing the EXACT pikabu_adapter idioms):
1. Launches a visible Chromium with the persistent profile `.pikabu-profile`
   (same as src/pikabu_adapter.PROFILE_DIR) and opens the editor at
   https://pikabu.ru/add (pikabu_adapter.ADD_URL).
2. Pastes the literal body HTML "<h2>Level two</h2><h3>Level three</h3>" into the
   editor using the SAME synthetic ClipboardEvent paste as
   pikabu_adapter._paste_html (replicated below verbatim).
3. Dumps to stdout + experiments/05-heading-levels/pikabu_after_paste.json:
   the count of h1/h2/h3 inside `.tiptap.ProseMirror`, and for each heading node
   found, its tag name + className.
4. Keeps the browser open at the end for manual inspection.

This is a DISCOVERY probe — it requires an already-authenticated .pikabu-profile
and must be run by hand.
"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# Reuse the EXACT profile dir / URL / body selector from the real Pikabu adapter.
PROFILE_DIR = ".pikabu-profile"
ADD_URL = "https://pikabu.ru/add"
BODY_SEL = ".tiptap.ProseMirror"
BODY_HTML = "<h2>Level two</h2><h3>Level three</h3>"
OUT = Path("experiments/05-heading-levels/pikabu_after_paste.json")


def _paste_html(page, html):
    """Insert body HTML via a synthetic paste event — VERBATIM from
    pikabu_adapter._paste_html (Tiptap keeps it high-fidelity)."""
    page.evaluate(
        """(html) => {
            const el = document.querySelector('.tiptap.ProseMirror');
            el.focus();
            const dt = new DataTransfer();
            dt.setData('text/html', html);
            dt.setData('text/plain', html.replace(/<[^>]+>/g, ''));
            el.dispatchEvent(new ClipboardEvent('paste',
                {clipboardData: dt, bubbles: true, cancelable: true}));
        }""",
        html,
    )


# Count h1/h2/h3 inside the editor and report each heading node's tag + class.
_DUMP_HEADINGS_JS = r"""
() => {
  const root = document.querySelector('.tiptap.ProseMirror');
  const headings = root
    ? Array.from(root.querySelectorAll('h1, h2, h3')).map(h => ({
        tag: h.tagName.toLowerCase(),
        className: h.className,
        text: (h.innerText || '').trim(),
      }))
    : [];
  const count = {
    h1: root ? root.querySelectorAll('h1').length : 0,
    h2: root ? root.querySelectorAll('h2').length : 0,
    h3: root ? root.querySelectorAll('h3').length : 0,
  };
  return {count, headings};
}
"""


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print(f"Opening {ADD_URL} ...", flush=True)
        page.goto(ADD_URL, wait_until="domcontentloaded")
        page.wait_for_selector(BODY_SEL, timeout=30000)
        time.sleep(2)

        print(f"Pasting body HTML: {BODY_HTML!r}", flush=True)
        page.click(BODY_SEL)
        _paste_html(page, BODY_HTML)
        time.sleep(1.0)

        data = page.evaluate(_DUMP_HEADINGS_JS)
        pretty = json.dumps(data, ensure_ascii=False, indent=2)
        print(pretty, flush=True)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(pretty, encoding="utf-8")
        print(f"\nWrote heading dump to {OUT}", flush=True)

        print("Browser left open for inspection.", flush=True)
        try:
            input("Press Enter here to close the browser...")
        except EOFError:
            time.sleep(30)
        ctx.close()


if __name__ == "__main__":
    main()

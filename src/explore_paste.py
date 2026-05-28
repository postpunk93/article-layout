"""Test whether the VC Editor.js converts pasted HTML into proper blocks.

Usage: python -m src.explore_paste

Opens the editor, types a title, moves into the body, then pastes a small
HTML sample two ways (clipboard+Ctrl+V, and a dispatched paste event with a
DataTransfer carrying text/html). Dumps the resulting block structure so we can
see whether <h2> -> header block, <p> -> paragraph, <strong>/<em> survive, and
whether our [[IMG:...]] markers survive as plain paragraph text.
"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE_DIR = ".vc-profile"
EDITOR_URL = "https://vc.ru/?modal=editor"
OUT = Path("experiments/03-vc-editor/capture")
TITLE_SEL = 'div.editor-tool-input[data-placeholder="Заголовок"]'

SAMPLE_HTML = (
    "<h2>Раздел первый</h2>"
    "<p>Обычный текст, потом <strong>жирный</strong> и <em>курсив</em>.</p>"
    "<p>[[IMG:image5.png]]</p>"
    "<p>Второй абзац после маркера.</p>"
)

_BLOCKS_JS = r"""
() => {
  const ed = document.querySelector('.codex-editor');
  const blocks = ed ? Array.from(ed.querySelectorAll('.ce-block')).map(b => {
    const ce = b.querySelector('[contenteditable="true"]');
    return {
      cls: b.className,
      tool: (b.querySelector('[class*="-tool"]') || {}).className || '',
      text: (ce ? ce.innerText : b.innerText || '').trim().slice(0, 80),
      innerHTML: (ce ? ce.innerHTML : '').slice(0, 200),
    };
  }) : [];
  return {url: location.href, count: blocks.length, blocks};
}
"""


def dump_blocks(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    data = page.evaluate(_BLOCKS_JS)
    (OUT / f"{name}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    page.screenshot(path=str(OUT / f"{name}.png"))
    print(f"{name}: {data['count']} blocks", flush=True)
    for b in data["blocks"]:
        print(f"   tool={b['tool'][:40]!r} text={b['text'][:40]!r}", flush=True)


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(EDITOR_URL)
        page.wait_for_selector(TITLE_SEL, timeout=30000)
        time.sleep(2)

        page.click(TITLE_SEL)
        page.keyboard.type("ТЕСТ вставки")
        page.keyboard.press("Enter")  # move into body
        time.sleep(1)

        # --- Attempt 1: clipboard write (text/html) + Ctrl+V ---
        print("Attempt 1: clipboard ClipboardItem(text/html) + Ctrl+V", flush=True)
        try:
            page.evaluate(
                """async (html) => {
                    const item = new ClipboardItem({
                        'text/html': new Blob([html], {type: 'text/html'}),
                        'text/plain': new Blob([html], {type: 'text/plain'}),
                    });
                    await navigator.clipboard.write([item]);
                }""",
                SAMPLE_HTML,
            )
            page.keyboard.press("Control+V")
            time.sleep(2)
            dump_blocks(page, "paste1_clipboard")
        except Exception as exc:
            print(f"  attempt 1 failed: {exc}", flush=True)

        print("Done. Closing in 4s.", flush=True)
        time.sleep(4)
        ctx.close()


if __name__ == "__main__":
    main()

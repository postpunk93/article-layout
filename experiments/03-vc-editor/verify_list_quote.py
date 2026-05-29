"""Task 8 (focused): verify list + quote insertion in isolation.

Builds a small Document (heading, paragraph, unordered list, paragraph, ordered
list, quote, paragraph) via vc_adapter.build_document, screenshots the result,
and dumps the block sequence so we can confirm:
- unordered list renders bulleted with the right items,
- ordered list renders numbered (editor-list-tool--ordered),
- quote renders as a quote block,
- block ORDER matches the document.
Keeps the browser open ~3 min. Stops at a saved draft (never publishes).
"""
import os
import sys
import time
from pathlib import Path

# Allow running this script directly: put the repo root (three levels up) on the
# import path so `import src...` works regardless of the current directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from playwright.sync_api import sync_playwright

from src.ir import Document, Heading, Paragraph, ListBlock, ListItem, Quote, Run
from src import vc_adapter

CAP = Path("experiments/03-vc-editor/capture")


def R(t):
    return [Run(text=t)]


DOC = Document(
    title="VERIFY list+quote",
    blocks=[
        Heading(level=2, runs=R("Раздел один")),
        Paragraph(runs=R("Вступительный абзац перед списком.")),
        ListBlock(ordered=False, items=[
            ListItem(runs=R("первый маркированный")),
            ListItem(runs=R("второй маркированный")),
            ListItem(runs=R("третий маркированный")),
        ]),
        Paragraph(runs=R("Абзац между списками.")),
        ListBlock(ordered=True, items=[
            ListItem(runs=R("шаг один")),
            ListItem(runs=R("шаг два")),
            ListItem(runs=R("шаг три")),
            ListItem(runs=R("шаг четыре")),
        ]),
        Quote(runs=R("Это цитата, которая должна стать настоящим блоком цитаты.")),
        Paragraph(runs=R("Заключительный абзац после цитаты.")),
    ],
)


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            vc_adapter.PROFILE_DIR, headless=False,
            args=["--start-maximized"], no_viewport=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            vc_adapter.build_document(page, DOC, Path("example/lists-quotes/images"))
        except Exception as e:
            print("BUILD FAILED:", repr(e)[:200], flush=True)
        time.sleep(1.0)
        CAP.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(CAP / "verify_full.png"), full_page=True)
        (CAP / "verify_editor.html").write_text(
            page.eval_on_selector(".codex-editor", "el=>el.outerHTML"), encoding="utf-8")
        # report the block sequence (content tool of each block)
        seq = page.evaluate("""() => {
            const out = [];
            for (const b of document.querySelectorAll('.codex-editor .ce-block')) {
                const c = b.querySelector('.ce-block__content');
                const ul = c && c.querySelector('ul,ol');
                let kind = 'text/other';
                if (c && c.querySelector('.editor-header-tool')) kind = 'header';
                else if (ul) kind = ul.classList.contains('editor-list-tool--ordered') ? 'list-ordered' : 'list-unordered';
                else if (c && c.querySelector('.editor-quote-tool')) kind = 'quote';
                else if (c && c.querySelector('.editor-text-tool')) kind = 'paragraph';
                out.push(kind + ' :: ' + (c ? c.innerText : '').replace(/\\n/g,' | ').slice(0,50));
            }
            return out;
        }""")
        print("BLOCK SEQUENCE:", flush=True)
        for i, s in enumerate(seq):
            print(f"  {i}: {ascii(s)}", flush=True)
        print("VERIFY DONE. URL:", page.url, flush=True)
        print("Browser open ~3 min for visual check.", flush=True)
        time.sleep(180)
        ctx.close()


if __name__ == "__main__":
    main()

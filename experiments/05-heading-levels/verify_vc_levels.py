"""Verify Task 3: VC adapter inserts H2 (level 2) and H3 (level 3) correctly.

Usage: python experiments/05-heading-levels/verify_vc_levels.py

Parses the minimal in/headtest/index.html (H1 title + one H2 + one H3, no images),
drives the real vc_adapter.build_document, then dumps the resulting heading tags
from the Editor.js DOM to confirm the H3 block landed as <h3>, not <h2>.

Requires an authenticated .vc-profile. Run by hand.
"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from src.parser import parse
from src import vc_adapter

DOC_DIR = Path("in/headtest")
OUT = Path("experiments/05-heading-levels/vc_levels_after_build.json")

_DUMP_JS = r"""
() => {
  // VC's Editor.js renders heading blocks as custom (non-semantic) DOM, so dump each
  // top-level .ce-block: its data-type-ish wrapper class, the tag+class of its inner
  // content element, and a text preview. The two heading blocks should differ in a
  // way that distinguishes level 2 from level 3.
  const root = document.querySelector('.codex-editor');
  const blocks = root ? Array.from(root.querySelectorAll('.ce-block')).map(b => {
    const content = b.querySelector('.ce-block__content') || b;
    return {
      text: (b.innerText || '').trim().slice(0, 40),
      html: content.innerHTML.slice(0, 200),
    };
  }) : null;
  return {rootFound: !!root, blocks};
}
"""


def main():
    doc = parse((DOC_DIR / "index.html").read_text(encoding="utf-8"))
    print(f"Parsed: title={doc.title!r}, blocks={len(doc.blocks)}", flush=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            vc_adapter.PROFILE_DIR, headless=False,
            args=["--start-maximized"], no_viewport=True,
        )
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        vc_adapter.build_document(page, doc, DOC_DIR / "images")
        # The editor stays mounted on the saved-draft (action=edit) view; wait for a
        # heading block to be present before dumping so we don't catch a transient DOM.
        try:
            page.wait_for_selector(".codex-editor .ce-block", timeout=10000)
        except Exception:
            print("WARNING: no .codex-editor .ce-block found within 10s", flush=True)
        time.sleep(1.0)

        data = page.evaluate(_DUMP_JS)
        pretty = json.dumps(data, ensure_ascii=False, indent=2)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(pretty, encoding="utf-8")
        # Console is cp1251 here; print an ASCII-safe view and rely on the utf-8 file.
        print(pretty.encode("ascii", "backslashreplace").decode(), flush=True)
        print(f"\nWrote {OUT}", flush=True)

        try:
            input("Press Enter here to close the browser...")
        except EOFError:
            time.sleep(20)
        ctx.close()


if __name__ == "__main__":
    main()

"""Claude-driven exploration of the VC Editor.js editor (login persisted).

Usage: python -m src.explore_vc

Opens the editor directly at https://vc.ru/?modal=editor (already authenticated
via the .vc-profile persistent context), then drives a short sequence and dumps
the editor's block structure + toolbox items so we can learn the body/image
selectors. Does NOT click the image tool (that would open a native file dialog);
image upload is handled later via Playwright's file-chooser interception.

Dumps to experiments/03-vc-editor/capture/step_*.json and step_*.png .
"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE_DIR = ".vc-profile"
EDITOR_URL = "https://vc.ru/?modal=editor"
OUT = Path("experiments/03-vc-editor/capture")
TITLE_SEL = 'div.editor-tool-input[data-placeholder="Заголовок"]'

_DUMP_JS = r"""
() => {
  const ed = document.querySelector('.codex-editor');
  const trunc = (s, n) => (s || '').slice(0, n);
  const blocks = ed ? Array.from(ed.querySelectorAll('.ce-block')).map(b => ({
    cls: b.className,
    html: trunc(b.innerHTML, 400),
  })) : [];
  const editables = Array.from(document.querySelectorAll('[contenteditable="true"]')).map(e => ({
    cls: e.className,
    ph: e.getAttribute('data-placeholder'),
    text: trunc(e.innerText, 80),
  }));
  // Any element whose class hints at a toolbox/popover/menu — exploratory.
  const hint = (el) => /toolbox|popover|menu|tool-/i.test(el.className || '');
  const toolbox = Array.from(document.querySelectorAll('*')).filter(hint).map(i => ({
    tag: i.tagName.toLowerCase(),
    cls: i.className,
    text: trunc((i.innerText || i.getAttribute('aria-label') || ''), 50).trim(),
    data: Object.assign({}, i.dataset),
    visible: !!(i.getBoundingClientRect().width),
  })).slice(0, 60);
  // Full HTML of likely toolbox/popover containers for structure inspection.
  const containers = Array.from(document.querySelectorAll(
    '.ce-popover, .ce-toolbox, [class*="popover"], [class*="toolbox"]'
  )).map(c => ({cls: c.className, html: trunc(c.outerHTML, 1500)})).slice(0, 6);
  const files = Array.from(document.querySelectorAll('input[type="file"]')).map(f => ({
    cls: f.className, accept: f.accept, name: f.name,
  }));
  return {url: location.href, blocks, editables, toolbox, containers, files};
}
"""


def dump(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(OUT / f"{name}.png"))
    except Exception as exc:
        print(f"  (screenshot {name} failed: {exc})", flush=True)
    data = page.evaluate(_DUMP_JS)
    (OUT / f"{name}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{name}: blocks={len(data['blocks'])} editables={len(data['editables'])} "
          f"toolbox={len(data['toolbox'])} files={len(data['files'])} url={data['url']}",
          flush=True)


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
        dump(page, "step1_open")

        # Type a title.
        print("Typing title...", flush=True)
        page.click(TITLE_SEL)
        page.keyboard.type("ТЕСТ: заголовок разведки")
        time.sleep(1)

        # Move into the body and type a paragraph (Enter from title usually
        # creates the first body block in Editor.js).
        print("Entering body and typing a paragraph...", flush=True)
        page.keyboard.press("Enter")
        time.sleep(0.5)
        page.keyboard.type("Первый абзац тела для разведки структуры блоков.")
        time.sleep(1)
        dump(page, "step2_typed")

        # Create a NEW empty block — Editor.js shows the '+' on an empty block.
        print("Creating an empty block (Enter) so the '+' becomes visible...", flush=True)
        page.keyboard.press("Enter")
        time.sleep(1)
        dump(page, "step3_empty_block")

        # Open the add-block toolbox via the '+'.
        print("Opening the '+' toolbox...", flush=True)
        opened = False
        try:
            page.click(".ce-toolbar__plus", timeout=5000)
            opened = True
        except Exception as exc:
            print(f"  (plus click failed: {exc})", flush=True)
            # Fallback: force the underlying button via JS.
            try:
                page.eval_on_selector(".ce-toolbar__plus", "el => el.click()")
                opened = True
                print("  (opened via JS .click())", flush=True)
            except Exception as exc2:
                print(f"  (JS click failed too: {exc2})", flush=True)
        time.sleep(1.5)
        dump(page, "step4_toolbox")
        print(f"toolbox opened={opened}", flush=True)

        # Insert an image: intercept the native file chooser that the 'media'
        # toolbox item opens (triggered via a JS .click()), and set our file.
        print("Inserting image via [data-type=media] + file chooser...", flush=True)
        try:
            with page.expect_file_chooser(timeout=8000) as fc:
                page.eval_on_selector('.ce-toolbox__item[data-type="media"]', "el => el.click()")
            fc.value.set_files("example/images/image5.png")
            print("  file set on chooser.", flush=True)
        except Exception as exc:
            print(f"  image insert failed: {exc}", flush=True)
        # Wait for upload + render.
        time.sleep(10)
        dump(page, "step6_image_uploaded")

        print("Done. Closing in 4s.", flush=True)
        time.sleep(4)
        ctx.close()


if __name__ == "__main__":
    main()

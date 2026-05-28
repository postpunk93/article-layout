"""Drive the VC (Editor.js) editor to build a draft from a parsed Document.

The editor is Editor.js. We build the body block-by-block (paste is lossy), using
the selectors recorded in experiments/03-vc-editor/notes.md:
- Title block:   div.editor-tool-input[data-placeholder="Заголовок"]
- Add-block "+":  .ce-toolbar__plus  (only on an EMPTY block)
- Toolbox items:  li.ce-toolbox__item[data-type="text|header|media|..."]
- Image caption:  .editor-tool-input--text-sm  (per image block)
- Saved draft:    URL gains  ?...&id=<NNN>

Visible browser, persistent profile, STOPS at a saved draft (never publishes).
"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from src.ir import Heading, Paragraph, Image

PROFILE_DIR = ".vc-profile"
EDITOR_URL = "https://vc.ru/?modal=editor"
TITLE_SEL = 'div.editor-tool-input[data-placeholder="Заголовок"]'
TOOLBOX_OPEN_SEL = ".ce-popover.ce-toolbox.opened"
CAPTION_SEL = ".editor-tool-input--text-sm"


def _type_runs(page, runs):
    """Type runs, toggling bold/italic via Ctrl+B / Ctrl+I per run."""
    for r in runs:
        if r.bold:
            page.keyboard.press("Control+b")
        if r.italic:
            page.keyboard.press("Control+i")
        page.keyboard.type(r.text)
        if r.italic:
            page.keyboard.press("Control+i")
        if r.bold:
            page.keyboard.press("Control+b")


def _open_toolbox(page):
    page.click(".ce-toolbar__plus", timeout=5000)
    page.wait_for_selector(TOOLBOX_OPEN_SEL, timeout=5000)


def _insert_heading(page, runs):
    _open_toolbox(page)
    # The first [data-type="header"] toolbox item is H2.
    page.eval_on_selector_all(
        '.ce-toolbox__item[data-type="header"]', "els => els[0].click()"
    )
    time.sleep(0.4)
    _type_runs(page, runs)


def _insert_image(page, image_path, caption_runs):
    # Count existing images so we can wait for THIS upload to actually land.
    n_before = page.evaluate(
        "() => document.querySelectorAll('.codex-editor .ce-block img').length"
    )
    _open_toolbox(page)
    with page.expect_file_chooser(timeout=10000) as fc:
        page.eval_on_selector('.ce-toolbox__item[data-type="media"]', "el => el.click()")
    fc.value.set_files(str(image_path))
    # CRITICAL: image upload is async. Wait until a NEW image block exists and its
    # <img> has finished loading a real http(s) src. Without this, subsequent
    # paragraphs are typed while the upload is in flight and the image lands at the
    # moved caret — scrambling block order in image-dense regions.
    page.wait_for_function(
        """(n) => {
            const imgs = document.querySelectorAll('.codex-editor .ce-block img');
            if (imgs.length <= n) return false;
            const last = imgs[imgs.length - 1];
            return last.complete && last.naturalWidth > 0 &&
                   /^https?:/.test(last.currentSrc || last.src || '');
        }""",
        arg=n_before,
        timeout=60000,
    )
    # Caption belongs to the just-added (now last) image block.
    page.locator(CAPTION_SEL).last.click()
    if caption_runs:
        page.keyboard.type("".join(r.text for r in caption_runs))


def build_document(page, doc, images_dir: Path, log=print):
    log(f"Opening editor: {EDITOR_URL}")
    page.goto(EDITOR_URL)
    page.wait_for_selector(TITLE_SEL, timeout=30000)
    time.sleep(2)

    log(f"Title: {doc.title!r}")
    page.click(TITLE_SEL)
    page.keyboard.type(doc.title)
    page.keyboard.press("Enter")  # move into the body (creates first empty block)
    time.sleep(0.5)

    last = len(doc.blocks) - 1
    for i, block in enumerate(doc.blocks):
        if isinstance(block, Heading):
            log(f"[{i}] heading: {''.join(r.text for r in block.runs)[:50]!r}")
            _insert_heading(page, block.runs)
        elif isinstance(block, Paragraph):
            log(f"[{i}] paragraph ({len(block.runs)} runs)")
            _type_runs(page, block.runs)
        elif isinstance(block, Image):
            path = images_dir / block.file
            if not path.exists():
                log(f"[{i}] IMAGE MISSING ON DISK: {path} — pausing")
                input("Fix the image then press Enter to continue...")
            log(f"[{i}] image: {block.file} caption={'yes' if block.caption else 'no'}")
            _insert_image(page, path, block.caption)
        # Enter creates the next empty block (needed for the next heading/image's
        # toolbox, and to leave an image's caption). Skip it after the last block
        # so we don't leave a trailing empty paragraph.
        if i < last:
            page.keyboard.press("Enter")
        time.sleep(0.3)

    # Confirm the draft saved (URL gains an id=NNN).
    try:
        page.wait_for_function("() => location.href.includes('id=')", timeout=15000)
        log(f"Draft saved: {page.url}")
    except Exception:
        log(f"WARNING: did not detect saved-draft URL; current: {page.url}")


def run_document(images_dir: Path, doc, keep_open=True):
    """Launch a visible, authenticated browser and build the draft. Stops there."""
    images_dir = Path(images_dir)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        # Auth persists in the profile. If the editor doesn't open (not logged
        # in), build_document's wait for the title selector raises with a clear
        # error and the visible window stays for inspection.
        build_document(page, doc, images_dir)
        print("Done — draft built. Review it in the browser and publish manually.")
        if keep_open:
            try:
                input("Press Enter here to close the browser...")
            except EOFError:
                # No interactive stdin (e.g. launched headless from a harness):
                # keep the window up briefly instead of closing instantly.
                time.sleep(15)
        ctx.close()

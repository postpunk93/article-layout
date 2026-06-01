"""Drive LiveJournal's new post editor (Draft.js) to build an autosaved draft.

See docs/plans/2026-06-02-lj-adapter-design.md. The body editor is Draft.js (like
Dzen): one real clipboard paste of clean HTML carries headings/paragraphs/bold/
italic/quotes/lists; only images need a native-upload pass; stop at autosave, never
publish.
"""
import time
from pathlib import Path

from src.emit_html import emit_body
from src.ir import Image

POST_URL = "https://www.livejournal.com/post/"
BODY_SEL = '.public-DraftEditor-content[contenteditable="true"]'
TITLE_SEL = "textarea.js--post-title"
PUBLISH_SEL = "button.js--toggle-submission-popup"   # NEVER click — publish flow
# PLupload image inputs (probe b, verified live): two share this accept list — the
# multiple one (nth 0) and a single one (nth 1). set_input_files on the SINGLE input
# uploads at the current Draft.js cursor (the emptied marker block); no slash menu /
# file-chooser needed. Inputs are created at editor load, always present.
IMAGE_INPUT_SEL = 'input[type=file][accept*=".webp"]'
CAPTION_SEL = 'textarea[class*="caption"]'           # native image caption ("Введите описание картинки")
# Logged-in marker: the Draft.js body mounts only for an authenticated user.
ALIVE_SEL = BODY_SEL


def body_html(doc):
    """Clean body HTML for the paste: real <blockquote> (LJ makes a native quote
    block), images as [[IMG:file]] markers replaced after the paste.

    Probe (a), verified live: a pasted <blockquote> becomes a native Draft.js
    <blockquote data-block="true"> quote block, and <ul>/<ol> become native
    list-item blocks — no post-paste convert pass is needed (unlike VC)."""
    return emit_body(doc, caption_marker=False, quote_as_paragraph=False, img_sep=":")


def _open_editor(page, log):
    """Open a fresh post editor, dismiss the restore-draft modal, return when the
    body contenteditable is present."""
    log("Opening LiveJournal post editor…")
    page.goto(POST_URL, wait_until="domcontentloaded")
    page.wait_for_selector(BODY_SEL, timeout=30000)  # logged-in marker
    page.wait_for_timeout(1200)
    # "Открыть последний черновик?" — start clean, decline restoring the old draft.
    for sel in ["text=Нет, спасибо", '[aria-label="Modal Window Close"]']:
        loc = page.locator(sel)
        if loc.count():
            log("Dismissing restore-draft modal.")
            loc.first.click()
            page.wait_for_timeout(600)
            break
    log(f"Editor ready: {page.url}")


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


def _set_title_and_body(page, doc, log):
    log(f"Title: {doc.title!r}")
    page.fill(TITLE_SEL, doc.title)
    # A real Ctrl+V only pastes into a FOCUSED tab; bring it to the foreground.
    page.bring_to_front()
    html = body_html(doc)
    _set_clipboard(page, html)
    page.click(BODY_SEL)
    page.wait_for_timeout(300)
    page.keyboard.press("Control+V")
    page.wait_for_timeout(1500)
    log("Body pasted.")


def _replace_marker_with_image(page, block, path, log):
    needle = f"[[IMG:{block.file}]]"
    # Find and focus the marker block, then clear its text so the upload lands in place.
    idx = page.evaluate(
        """(needle) => {
            const bs = [...document.querySelectorAll('[data-block="true"]')];
            return bs.findIndex(el => (el.innerText || '').includes(needle));
        }""",
        needle,
    )
    if idx < 0:
        log(f"  marker {needle} not found — skipping")
        return
    block_loc = page.locator('[data-block="true"]').nth(idx)
    block_loc.scroll_into_view_if_needed()
    block_loc.click()
    # Let the Draft.js selection settle in this block before clearing. Without this,
    # the caret can still be in the PREVIOUS image's caption textarea (we just typed
    # there), so Home/Shift+End/Delete miss and the upload lands at the stale caret —
    # leaving this marker behind and the image misplaced.
    page.wait_for_timeout(200)
    # Empty ONLY this marker block. DraftJS treats Ctrl+A as "select the whole editor",
    # so Ctrl+A + Delete would wipe the entire body — select just this line instead.
    # Retry the clear until the marker text is actually gone (the caret may have needed
    # an extra beat to land here). Safe to repeat — the image hasn't uploaded yet.
    for _ in range(3):
        page.keyboard.press("Home")
        page.keyboard.press("Shift+End")
        page.keyboard.press("Delete")
        if needle not in page.evaluate("() => document.querySelector('.public-DraftEditor-content').innerText"):
            break
        block_loc.click()
        page.wait_for_timeout(200)
    n_before = page.evaluate("() => document.querySelectorAll('.public-DraftEditor-content img').length")
    # The single PLupload input uploads at the cursor (this emptied block); set_input_files
    # dispatches the change event PLupload listens for — no slash menu / file chooser.
    page.locator(IMAGE_INPUT_SEL).nth(1).set_input_files(str(path))
    # Wait for the uploaded image to get a real CDN src (ic.pics.livejournal.com).
    page.wait_for_function(
        """(n) => {
            const imgs = document.querySelectorAll('.public-DraftEditor-content img');
            if (imgs.length <= n) return false;
            const last = imgs[imgs.length - 1];
            return last.complete && last.naturalWidth > 0 && /^https?:/.test(last.currentSrc || last.src || '');
        }""",
        arg=n_before,
        timeout=60000,
    )
    log(f"  image: {block.file} caption={'yes' if block.caption else 'no'}")
    if block.caption:
        # Images upload in document order, so the just-added figure's caption textarea
        # is the last one in the DOM.
        cap_loc = page.locator(CAPTION_SEL).last
        cap_loc.click()
        page.keyboard.type("".join(r.text for r in block.caption))
    time.sleep(0.3)

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
    # Place the caret INSIDE this marker block and VERIFY it landed before deleting
    # anything. The caret can lag behind the click — e.g. it's still in the previous
    # image's caption textarea we just typed into — and a blind Home/Shift+End/Delete
    # would then select and EAT whichever block the caret is really in (observed:
    # the preceding paragraph losing its opening words). Re-click until getSelection's
    # anchor is in THIS block; only then delete.
    placed = False
    for _ in range(6):
        block_loc.click()
        page.wait_for_timeout(150)
        placed = block_loc.evaluate(
            """(el) => {
                const s = window.getSelection();
                let n = s && s.anchorNode;
                while (n && n !== el) n = n.parentElement;
                return !!n;
            }"""
        )
        if placed:
            break
    if not placed:
        log(f"  could not place caret in marker block for {block.file} — skipping")
        return
    # Caret confirmed in this single-line marker block. Select just this line and
    # delete it (Ctrl+A would select the WHOLE Draft.js editor). One pass is safe now —
    # the caret can't be in a sibling block.
    page.keyboard.press("Home")
    page.keyboard.press("Shift+End")
    page.keyboard.press("Delete")
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


def build_document(page, doc, images_dir, log=print):
    images_dir = Path(images_dir)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])

    _open_editor(page, log)
    _set_title_and_body(page, doc, log)

    images = [b for b in doc.blocks if isinstance(b, Image)]
    log(f"Uploading {len(images)} image(s)…")
    for block in images:
        path = images_dir / block.file
        if not path.exists():
            log(f"  IMAGE MISSING ON DISK: {path} — leaving marker [[IMG:{block.file}]]")
            continue
        try:
            _replace_marker_with_image(page, block, path, log)
        except Exception as e:  # noqa: BLE001 — report and continue
            log(f"  image {block.file} failed ({str(e)[:80]}) — marker left in body")

    # Stop at the autosaved draft — NEVER click PUBLISH_SEL. The footer "Черновики"
    # line gains "(сохранен в HH:MM:SS)" each time autosave completes. The URL gains
    # ?draft= right after the body paste — long before the images finish — so it is
    # NOT a safe signal; the footer timestamp is. Wait for it to ADVANCE past whatever
    # it read before the image edits, so we know the latest content is saved.
    # (The site renders the leading с as a Latin 'c', so match the ending "охранен в".)
    before = page.evaluate(
        r"() => { const m=(document.body.innerText||'').match(/охранен в [\d:]+/i); return m?m[0]:''; }"
    )
    try:
        page.wait_for_function(
            r"""(before) => {
                const m = (document.body.innerText || '').match(/охранен в [\d:]+/i);
                return !!m && m[0] !== before;
            }""",
            arg=before,
            timeout=40000,
        )
        log("Draft autosaved.")
    except Exception:  # noqa: BLE001
        log(f"WARNING: did not observe the saved indicator advance; draft may still be saving. URL: {page.url}")

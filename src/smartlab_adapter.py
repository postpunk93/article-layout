"""Drive smart-lab.ru's NEWER /topic/add2 editor (Editor.js) to build a draft.

smart-lab.ru has two post editors. The legacy ``/topic/add/`` is TinyMCE; the
newer ``/topic/add2`` is **Editor.js (Codex Editor)**. The Editor.js instance is
exposed as ``window.editor``, so instead of pasting the body and restoring lost
formatting with keyboard passes, we build the whole body deterministically via the
Editor.js JS API:

1. ``await window.editor.clear()`` — add2 AUTOSAVES and RESTORES a previous draft on
   load, so the editor is NOT empty. clear() removes the restored draft (leaving one
   empty block) so our render starts clean.
2. ``await window.editor.render({blocks:[…]})`` — render our blocks:
   - ``header`` level 1 -> ``h1.ce-header`` = the TITLE; level 2+ -> ``h2``…``h6``.
   - ``paragraph`` with inline ``<b>``/``<i>`` -> paragraph with bold/italic PRESERVED
     (no restore pass). We use ``<b>``/``<i>`` (NOT ``<strong>``/``<em>`` — the
     sanitizer may drop those).
   - ``list`` (style ``unordered``/``ordered``, flat string items) -> native list.
   - ``quote`` -> native ``blockquote.cdx-quote`` (no paragraph->quote conversion).
3. Images CANNOT go through render (they need an uploaded URL), so they stay as
   ``[[IMG file]]`` marker paragraphs and are then replaced by a native upload +
   caption (smart-lab uploads to https://smart-lab.ru/uploads/…).
4. add2 AUTOSAVES the draft (background POST to ``…/topic/autosave2/add/topic/``), so
   we STOP at the autosave — we NEVER click the «Опубликовать» control.
"""
import html
import time
from pathlib import Path

from src.ir import Heading, Paragraph, Image, ListBlock, Quote

HOME_URL = "https://smart-lab.ru/"
LOGIN_URL = "https://smart-lab.ru/login/"
ADD_URL = "https://smart-lab.ru/topic/add2"

# The editor mounts only for a logged-in user, so .codex-editor is the liveness
# marker (sessions.py navigates to ADD_URL and waits for ALIVE_SEL).
ALIVE_SEL = ".codex-editor"
# Opened toolbox popover (stock Editor.js v2).
TOOLBOX_OPEN_SEL = ".ce-popover--opened"
# Native image-block caption field.
CAPTION_SEL = ".image-tool__caption"


def _inline_html(runs):
    """Concatenate runs into inline HTML for Editor.js (escaped text, <b>/<i> only)."""
    out = []
    for r in runs:
        t = html.escape(r.text)
        if r.bold:
            t = f"<b>{t}</b>"
        if r.italic:
            t = f"<i>{t}</i>"
        out.append(t)
    return "".join(out)


def _doc_to_blocks(doc):
    """Build the Editor.js blocks JSON from the IR.

    Title -> header level 1 (add2's title is the first header block). Headings ->
    header (clamped to level 2+, since level 1 is the title). Images become
    [[IMG file]] marker paragraphs (replaced by a native upload afterwards, since
    render() can't carry un-uploaded images).
    """
    blocks = [{"type": "header", "data": {"text": html.escape(doc.title), "level": 1}}]
    for b in doc.blocks:
        if isinstance(b, Heading):
            level = min(max(b.level, 2), 6)
            blocks.append({"type": "header", "data": {"text": _inline_html(b.runs), "level": level}})
        elif isinstance(b, Paragraph):
            blocks.append({"type": "paragraph", "data": {"text": _inline_html(b.runs)}})
        elif isinstance(b, ListBlock):
            blocks.append({"type": "list", "data": {
                "style": "ordered" if b.ordered else "unordered",
                "items": [_inline_html(it.runs) for it in b.items]}})
        elif isinstance(b, Quote):
            blocks.append({"type": "quote", "data": {"text": _inline_html(b.runs), "caption": ""}})
        elif isinstance(b, Image):
            blocks.append({"type": "paragraph", "data": {"text": f"[[IMG {b.file}]]"}})
    return blocks


def _open_toolbox_on_active(page):
    """Open the '+' toolbox for the CURRENTLY active block.

    The caller must have placed the caret in the target (empty) block with a REAL
    click first — Editor.js anchors the toolbar on real caret events, and the real
    click also scrolls the block into view. The '+' button is never "visible" to
    Playwright (0-size until hover), so JS-click it; and the popover can render outside
    the viewport for a scrolled block, so wait for its opened state as ATTACHED
    (visible-waiting would time out).
    """
    page.eval_on_selector(".ce-toolbar__plus", "el => el.click()")
    page.wait_for_selector(TOOLBOX_OPEN_SEL, state="attached", timeout=5000)


def _replace_marker_with_image(page, block, path, log):
    """Find the [[IMG file]] marker paragraph, empty it, and upload a native image in
    its place (Editor.js strips <img>/data-URI on paste). The caption goes into the
    image block's native caption field. Marker uses a space (not a colon) — see
    emit_body. On add2 the image tool fires the OS file chooser DIRECTLY on click."""
    needle = f"[[IMG {block.file}]]"
    idx = page.evaluate(
        """(needle) => {
            const blocks = [...document.querySelectorAll('.codex-editor .ce-block')];
            return blocks.findIndex(el => (el.innerText || '').includes(needle));
        }""",
        needle,
    )
    if idx < 0:
        log(f"  marker {needle} not found — skipping")
        return
    block_loc = page.locator(".codex-editor .ce-block").nth(idx)
    block_loc.locator("[contenteditable]").first.click()  # anchor toolbar to this block
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")                          # empty the marker paragraph
    _open_toolbox_on_active(page)
    n_before = page.evaluate(
        "() => document.querySelectorAll('.codex-editor .ce-block img').length"
    )
    with page.expect_file_chooser(timeout=10000) as fc:
        page.eval_on_selector('.ce-popover-item[data-item-name="image"]', "el => el.click()")
    fc.value.set_files(str(path))
    # Upload is async — wait for a NEW image that has a real http(s) src
    # (smart-lab rewrites the src to https://smart-lab.ru/uploads/… after upload).
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
    log(f"  image: {block.file} caption={'yes' if block.caption else 'no'}")
    if block.caption:
        block_loc.locator(CAPTION_SEL).first.click()
        page.keyboard.type("".join(r.text for r in block.caption))
    time.sleep(0.3)


def build_document(page, doc, images_dir, log=print):
    images_dir = Path(images_dir)

    log(f"Opening editor: {ADD_URL}")
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.goto(ADD_URL)
    page.wait_for_selector(ALIVE_SEL, timeout=30000)
    time.sleep(2)

    # add2 autosaves & RESTORES a prior draft on load — clear it so we start clean.
    log("Clearing any restored draft…")
    page.evaluate("async () => { await window.editor.clear(); }")

    # Render the whole body via the Editor.js API: title -> h1, headings -> h2+,
    # paragraphs/lists/quotes native with inline <b>/<i> preserved. Images are
    # [[IMG file]] marker paragraphs, replaced by a native upload below.
    log(f"Title: {doc.title!r}")
    blocks = _doc_to_blocks(doc)
    log(f"Rendering {len(blocks)} blocks via editor.render…")
    page.evaluate("async (blocks) => { await window.editor.render({blocks}); }", blocks)
    time.sleep(1.0)

    # Images: replace each [[IMG file]] marker with a native upload + caption.
    # Best-effort per image — a failure must not abort the rest.
    images = [b for b in doc.blocks if isinstance(b, Image)]
    log(f"Uploading {len(images)} image(s)…")
    for block in images:
        path = images_dir / block.file
        if not path.exists():
            log(f"  IMAGE MISSING ON DISK: {path} — leaving marker [[IMG {block.file}]]")
            continue
        try:
            _replace_marker_with_image(page, block, path, log)
        except Exception as e:  # noqa: BLE001
            log(f"  image {block.file} failed ({str(e)[:80]}) — marker left in body")

    # Stop at the autosaved draft — NEVER click «Опубликовать». add2 fires a
    # background POST to …/topic/autosave2/add/topic/ as you edit; wait for it.
    try:
        with page.expect_request(
            lambda r: "autosave2/add/topic" in r.url and r.method == "POST",
            timeout=15000,
        ):
            # Nudge: a tiny no-op caret move may trigger autosave; one may also be pending.
            try:
                page.locator(".codex-editor .ce-block [contenteditable]").first.click()
                page.keyboard.press("End")
            except Exception:  # noqa: BLE001
                pass
        log("Draft autosaved.")
    except Exception:  # noqa: BLE001
        log(f"WARNING: did not observe autosave request; draft may still be saving. URL: {page.url}")

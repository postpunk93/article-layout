"""Drive smart-lab.ru's NEWER /topic/add2 editor (Editor.js) to build a draft.

smart-lab.ru has two post editors. The legacy ``/topic/add/`` is TinyMCE; the
newer ``/topic/add2`` is **Editor.js (Codex Editor)** — the SAME engine as VC.
So this adapter is a near-clone of ``vc_adapter.py``: instead of typing the body
block-by-block, we insert the whole body with ONE real clipboard paste. A real
Ctrl+V (not a synthetic ClipboardEvent) is processed by Editor.js like a manual
paste, so paragraphs, H2/H3 headings and bullet/ordered lists survive. What paste
drops is restored afterwards:
- strong/em  -> re-applied by selecting char-offset ranges and pressing Ctrl+B/I
- quotes     -> the editor CANNOT convert a paragraph to a quote, so the paragraph
                is emptied and a native quote block is inserted in its place
- images     -> Editor.js strips <img>/data-URI on paste, so the body carries
                [[IMG file]] marker paragraphs; each is replaced by a native upload
                + caption (smart-lab uploads to https://smart-lab.ru/uploads/…)

Block addressing uses Editor.js's per-block ``data-id`` so the i-th IR block maps to
a unique, stable selector. On add2 the TITLE is the FIRST ``.ce-block`` (an
``h1.ce-header`` with placeholder «Заголовок»); body blocks are all the OTHERS, so we
exclude index 0 (pasted ``<h2>`` headings are ALSO ce-header, so excluding index 0 is
more robust than filtering by the placeholder like VC does).

add2 differs from VC only in CSS selectors (stock ``cdx-*`` / ``ce-popover-item``
classes instead of VC's customized ``editor-tool-input`` / ``ce-toolbox__item``) and
in the stop signal: add2 AUTOSAVES a draft (background POST to
``…/topic/autosave2/add/topic/``), so we STOP at the autosave — we NEVER click the
«Опубликовать» control (an ``<li>``).
"""
import time
from pathlib import Path

from src.emit_html import emit_body
from src.ir import Heading, Paragraph, Image, ListBlock, Quote

HOME_URL = "https://smart-lab.ru/"
LOGIN_URL = "https://smart-lab.ru/login/"
ADD_URL = "https://smart-lab.ru/topic/add2"

# The editor mounts only for a logged-in user, so .codex-editor is the liveness
# marker (sessions.py navigates to ADD_URL and waits for ALIVE_SEL).
ALIVE_SEL = ".codex-editor"
# Title = the FIRST .ce-block (h1.ce-header, placeholder «Заголовок»). Its editable
# is the contenteditable of the first block.
TITLE_SEL = ".codex-editor .ce-block:nth-of-type(1) [contenteditable]"
# Opened toolbox popover (stock Editor.js v2).
TOOLBOX_OPEN_SEL = ".ce-popover--opened"
# Native quote body field (placeholder «Enter a quote»).
QUOTE_BODY_SEL = ".cdx-quote__text"
# Native image-block caption field.
CAPTION_SEL = ".image-tool__caption"


def format_segments(runs):
    """Map runs to [(start, end, bold, italic)] char ranges needing formatting.

    Offsets are into the concatenated run text (what the pasted block contains).
    Runs with no bold/italic — and empty runs — produce no segment.
    """
    segments = []
    pos = 0
    for r in runs:
        end = pos + len(r.text)
        if r.text and (r.bold or r.italic):
            segments.append((pos, end, r.bold, r.italic))
        pos = end
    return segments


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


def _set_clipboard(page, html):
    """Put clean body HTML on the real clipboard via the async Clipboard API.

    Requires clipboard-write permission (granted in build_document). Writing our
    CLEAN html (not an execCommand copy of a styled offscreen div, which the browser
    bloats with inline styles) is what Editor.js parses into one block per element.
    The actual paste is a real Ctrl+V issued by the caller AFTER focusing the body —
    no JS may run between focusing the body and the paste, or the body caret is lost.
    """
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


def _select_range(page, container_selector, start, end):
    """Select [start, end) chars within the element matched by container_selector.

    Walks the element's text nodes by cumulative length to build a DOM Range, then
    sets it as the window selection so a following Ctrl+B/Ctrl+I formats it. Returns
    True if the range was selected, False if the element/offsets could not be matched
    (callers should skip the Ctrl+B/Ctrl+I keypress when this is False).
    """
    return page.evaluate(
        """({sel, start, end}) => {
            if (end <= start) return false;
            const root = document.querySelector(sel);
            if (!root) return false;
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
            let node, acc = 0, range = document.createRange(), setStart = false;
            while ((node = walker.nextNode())) {
                const len = node.textContent.length;
                if (!setStart && acc + len >= start) {
                    range.setStart(node, start - acc);
                    setStart = true;
                }
                if (setStart && acc + len >= end) {
                    range.setEnd(node, end - acc);
                    const s = window.getSelection();
                    s.removeAllRanges();
                    s.addRange(range);
                    return true;
                }
                acc += len;
            }
            return false;
        }""",
        {"sel": container_selector, "start": start, "end": end},
    )


def _body_block_ids(page):
    """data-id of each BODY block in document order, EXCLUDING the title block.

    On add2 the title is the FIRST .ce-block inside .codex-editor. Pasted body blocks
    are all the OTHER .ce-blocks. We exclude index 0 (NOT a placeholder filter like VC):
    a pasted <h2> heading is also a ce-header, so the placeholder rule is unreliable;
    excluding the first block is robust. Maps the i-th IR block to the i-th body block.
    """
    return page.evaluate(
        """() => [...document.querySelectorAll('.codex-editor .ce-block')]
            .slice(1)
            .map(b => b.dataset.id)"""
    )


def _block_sel(block_id):
    """CSS selector for a specific Editor.js block by its data-id."""
    return f'.codex-editor .ce-block[data-id="{block_id}"]'


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


def _format_list_items(page, block_id, list_block):
    """Re-apply strong/em inside each <li> of a pasted list block (per-item offsets)."""
    for k, item in enumerate(list_block.items):
        li_sel = _block_sel(block_id) + f" li:nth-of-type({k + 1})"
        for (s, e, b, it) in format_segments(item.runs):
            if _select_range(page, li_sel, s, e):
                if b:
                    page.keyboard.press("Control+b")
                if it:
                    page.keyboard.press("Control+i")


def _replace_paragraph_with_quote(page, block_id, quote):
    """Empty the paragraph at block_id and insert a native quote block in its place.

    The editor cannot convert a paragraph to a quote, so we clear the paragraph and
    build a quote block on the now-empty active block, typing the runs (which carries
    bold/italic inline). Deleting one paragraph and inserting one quote keeps the
    overall block count unchanged.
    """
    page.locator(_block_sel(block_id) + " [contenteditable]").first.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    _open_toolbox_on_active(page)
    page.eval_on_selector('.ce-popover-item[data-item-name="quote"]', "el => el.click()")
    page.wait_for_selector(QUOTE_BODY_SEL, state="attached", timeout=8000)
    page.locator(QUOTE_BODY_SEL).last.click(force=True)
    _type_runs(page, quote.runs)
    time.sleep(0.3)


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

    log(f"Title: {doc.title!r}")
    # 1. Paste the whole structure (quotes as <p>, images as [[IMG file]] markers).
    # Order is load-bearing: put the body on the clipboard FIRST, then type the title and
    # press Enter to drop into the body, then Ctrl+V — with NO JS between the title and
    # the paste (JS that touches the selection drops the body caret). The title is the
    # first .ce-block; Enter from it creates and focuses the first body block, and a real
    # Ctrl+V there is processed like a manual paste, so headings/paragraphs/lists survive.
    # We do NOT press End before Enter: a long title wraps to multiple lines and End goes
    # to the end of the current visual LINE, so Enter would split the title mid-way.
    # Typing leaves the caret at the true end of the title already, so Enter is clean.
    body_html = emit_body(doc, caption_marker=False, quote_as_paragraph=True, img_sep=" ")
    log("Pasting body via real clipboard…")
    _set_clipboard(page, body_html)
    page.locator(TITLE_SEL).first.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    page.keyboard.type(doc.title)
    page.keyboard.press("Enter")
    page.keyboard.press("Control+V")
    try:
        page.wait_for_function(
            """(n) => [...document.querySelectorAll('.codex-editor .ce-block')]
                .slice(1).length >= n""",
            arg=len(doc.blocks),
            timeout=15000,
        )
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.8)

    # 2. Validate the 1:1 block mapping (body blocks only — the title at index 0 is excluded).
    ids = _body_block_ids(page)
    positional_ok = len(ids) == len(doc.blocks)
    if not positional_ok:
        log(f"WARNING: block mapping off (expected {len(doc.blocks)}, got {len(ids)}); "
            f"skipping strong/em + quote passes — fix those by hand.")

    # 3a. Re-apply strong/em for non-reinserted blocks (paragraph/heading/list).
    if positional_ok:
        for i, block in enumerate(doc.blocks):
            if isinstance(block, (Heading, Paragraph)):
                sel = _block_sel(ids[i]) + " [contenteditable]"
                for (s, e, b, it) in format_segments(block.runs):
                    if _select_range(page, sel, s, e):
                        if b:
                            page.keyboard.press("Control+b")
                        if it:
                            page.keyboard.press("Control+i")
            elif isinstance(block, ListBlock):
                _format_list_items(page, ids[i], block)

    # 3b. Quotes: empty the paragraph at its position, insert a native quote block.
    # Best-effort per quote: a failure here must not abort the run (images still go in).
    if positional_ok:
        for i, block in enumerate(doc.blocks):
            if isinstance(block, Quote):
                log(f"[{i}] quote -> native quote block")
                try:
                    _replace_paragraph_with_quote(page, ids[i], block)
                except Exception as e:  # noqa: BLE001
                    log(f"  quote at block {i} failed ({str(e)[:80]}) — left as a paragraph")

    # 4. Images last (matched by marker content; conversion keeps block count).
    # Best-effort per image: a failure must not abort the rest.
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

    # 5. Confirm the draft autosaved. add2 fires a background POST to
    # …/topic/autosave2/add/topic/ as you edit — that is the saved-draft signal.
    # We do NOT click any save/publish control; the «Опубликовать» <li> is NEVER clicked.
    # The edits above may already have triggered (or be pending) an autosave; nudge it
    # with a tiny no-op caret move on the title and wait for the request.
    try:
        with page.expect_request(
            lambda r: "autosave2/add/topic" in r.url and r.method == "POST",
            timeout=15000,
        ):
            # Nudge autosave: a tiny no-op edit (focus + arrow) can trigger it; or one
            # may already be pending from the edits above.
            try:
                page.locator(TITLE_SEL).first.click()
                page.keyboard.press("End")
            except Exception:  # noqa: BLE001
                pass
        log("Draft autosaved.")
    except Exception:  # noqa: BLE001
        log(f"WARNING: did not observe autosave request; draft may still be saving. "
            f"URL: {page.url}")

"""Drive the VC (Editor.js) editor to build a draft from a parsed Document.

VC's editor is Editor.js (a block model). Instead of typing the body block-by-block,
we insert the whole body with ONE real clipboard paste: a real Ctrl+V (not a
synthetic ClipboardEvent) is processed by Editor.js like a manual paste, so
paragraphs, H2/H3 headings and bullet/ordered lists survive. What paste drops is
restored afterwards:
- strong/em  -> re-applied by selecting char-offset ranges and pressing Ctrl+B/I
- quotes     -> the editor CANNOT convert a paragraph to a quote, so the paragraph
                is emptied and a native quote block is inserted in its place
- images     -> VC strips <img>/data-URI on paste, so the body carries [[IMG:file]]
                marker paragraphs; each is replaced by a native upload + caption

Block addressing uses Editor.js's per-block ``data-id`` so the i-th IR block maps to a
unique, stable selector. Visible browser, persistent profile, STOPS at a saved draft
(never publishes).
"""
import time
from pathlib import Path

from src.emit_html import emit_body
from src.ir import Heading, Paragraph, Image, ListBlock, Quote

EDITOR_URL = "https://vc.ru/?modal=editor"
TITLE_SEL = 'div.editor-tool-input[data-placeholder="Заголовок"]'
TOOLBOX_OPEN_SEL = ".ce-popover.ce-toolbox.opened"
CAPTION_SEL = ".editor-tool-input--text-sm"
# Quote body is the multiline field; match on --multiline (stable across size classes).
QUOTE_BODY_SEL = ".editor-quote-tool .editor-tool-input--multiline"


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


def _paste_via_clipboard(page, html, expected_blocks):
    """Put body HTML on the real clipboard and paste it with a genuine Ctrl+V.

    Editor.js treats a real paste (unlike a synthetic ClipboardEvent) like a manual
    paste, so paragraphs/headings/lists survive. strong/em and quotes do not — they
    are restored in later passes.
    """
    page.evaluate(
        """(html) => {
            const div = document.createElement('div');
            div.contentEditable = 'true';
            div.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0';
            div.innerHTML = html;
            document.body.appendChild(div);
            const r = document.createRange();
            r.selectNodeContents(div);
            const s = window.getSelection();
            s.removeAllRanges();
            s.addRange(r);
            document.execCommand('copy');
            s.removeAllRanges();
            div.remove();
        }""",
        html,
    )
    # Put the caret inside the body, then paste for real.
    page.locator(".codex-editor .ce-block").first.click()
    page.keyboard.press("Control+V")
    # Wait for the pasted blocks to materialise (best-effort; mapping is validated later).
    try:
        page.wait_for_function(
            "(n) => document.querySelectorAll('.codex-editor .ce-block').length >= n",
            arg=expected_blocks,
            timeout=15000,
        )
    except Exception:
        pass


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


def _block_ids(page):
    """Editor.js tags each block wrapper with data-id; return them in document order
    so the i-th IR block can be addressed by a unique, stable selector."""
    return page.evaluate(
        "() => [...document.querySelectorAll('.codex-editor .ce-block')].map(b => b.dataset.id)"
    )


def _block_sel(block_id):
    """CSS selector for a specific Editor.js block by its data-id."""
    return f'.codex-editor .ce-block[data-id="{block_id}"]'


def _open_toolbox_on_active(page):
    """Open the '+' toolbox for the CURRENTLY active block.

    The caller must have placed the caret in the target (empty) block with a REAL
    click first — Editor.js anchors the toolbar on real caret events. Unlike a
    last-block-anchored open, this works for inserts in the MIDDLE of the document.
    """
    try:
        page.click(".ce-toolbar__plus", timeout=5000)
    except Exception:
        page.eval_on_selector(".ce-toolbar__plus", "el => el.click()")
    page.wait_for_selector(TOOLBOX_OPEN_SEL, timeout=5000)


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
    page.eval_on_selector('.ce-toolbox__item[data-type="quote"]', "el => el.click()")
    page.wait_for_selector(QUOTE_BODY_SEL, state="attached", timeout=8000)
    page.locator(QUOTE_BODY_SEL).last.click(force=True)
    _type_runs(page, quote.runs)
    time.sleep(0.3)


def _replace_marker_with_image(page, block, path, log):
    """Find the [[IMG:file]] marker paragraph, empty it, and upload a native image in
    its place (VC strips <img>/data-URI on paste). The caption goes into the image
    block's native caption field."""
    needle = f"[[IMG:{block.file}]]"
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
        page.eval_on_selector('.ce-toolbox__item[data-type="media"]', "el => el.click()")
    fc.value.set_files(str(path))
    # Upload is async — wait for a NEW image that has a real http(s) src.
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


def build_document(page, doc, images_dir: Path, log=print):
    log(f"Opening editor: {EDITOR_URL}")
    page.goto(EDITOR_URL)
    page.wait_for_selector(TITLE_SEL, timeout=30000)
    time.sleep(2)

    log(f"Title: {doc.title!r}")
    page.click(TITLE_SEL)
    page.keyboard.type(doc.title)
    time.sleep(0.3)

    # 1. Paste the whole structure (quotes as <p>, images as [[IMG:file]] markers).
    body_html = emit_body(doc, caption_marker=False, quote_as_paragraph=True)
    log("Pasting body via real clipboard…")
    _paste_via_clipboard(page, body_html, expected_blocks=len(doc.blocks))
    time.sleep(0.8)

    # 2. Validate the 1:1 block mapping.
    ids = _block_ids(page)
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
    if positional_ok:
        for i, block in enumerate(doc.blocks):
            if isinstance(block, Quote):
                log(f"[{i}] quote -> native quote block")
                _replace_paragraph_with_quote(page, ids[i], block)

    # 4. Images last (matched by marker content; conversion keeps block count).
    images = [b for b in doc.blocks if isinstance(b, Image)]
    log(f"Uploading {len(images)} image(s)…")
    for block in images:
        path = images_dir / block.file
        if not path.exists():
            log(f"  IMAGE MISSING ON DISK: {path} — leaving marker [[IMG:{block.file}]]")
            continue
        _replace_marker_with_image(page, block, path, log)

    # 5. Confirm the draft saved (URL gains an id=NNN).
    try:
        page.wait_for_function("() => location.href.includes('id=')", timeout=15000)
        log(f"Draft saved: {page.url}")
    except Exception:
        log(f"WARNING: did not detect saved-draft URL; current: {page.url}")

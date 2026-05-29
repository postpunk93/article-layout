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

from src.ir import Heading, Paragraph, Image, ListBlock, Quote

EDITOR_URL = "https://vc.ru/?modal=editor"
TITLE_SEL = 'div.editor-tool-input[data-placeholder="Заголовок"]'
TOOLBOX_OPEN_SEL = ".ce-popover.ce-toolbox.opened"
CAPTION_SEL = ".editor-tool-input--text-sm"
LIST_SEL = ".editor-list-tool"
LIST_ORDERED_SEL = ".editor-list-tool.editor-list-tool--ordered"
# Quote body is the multiline field; its size class flips between --text-xl
# (empty/short) and --text-lg (longer), so match on --multiline, which is stable.
# The author/source field is the sibling --text-sm (no --multiline) — left empty.
QUOTE_BODY_SEL = ".editor-quote-tool .editor-tool-input--multiline"
# The author/source field: single-line --text-sm (no --multiline). Left empty,
# but used to EXIT the quote — Enter in the multiline body only adds a newline;
# Enter in this single-line field leaves the block (like an image caption).
QUOTE_AUTHOR_SEL = ".editor-quote-tool .editor-tool-input--text-sm"
BLOCK_SETTINGS_ITEM_SEL = ".ce-block-settings__item"
SETTINGS_TOGGLER_SEL = ".ce-block-action__settings-toggler"
ORDERED_TUNE_LABEL = "Нумерованный"


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


def _open_toolbox(page):
    # Anchor the toolbar to the current (last) block with a REAL click first.
    # After a list/quote the trailing empty paragraph carries a stray zero-width
    # char and the toolbar is left stale, so the "+" opens the toolbox hidden /
    # mispositioned. A real click repositions the toolbar to that block.
    try:
        page.locator(".codex-editor .ce-block").last.click()
    except Exception:
        pass
    # Right after a custom block, the "+" may report as "not visible" to the
    # normal click. Fall back to a JS click before waiting for the toolbox.
    try:
        page.click(".ce-toolbar__plus", timeout=5000)
    except Exception:
        page.eval_on_selector(".ce-toolbar__plus", "el => el.click()")
    page.wait_for_selector(TOOLBOX_OPEN_SEL, timeout=5000)


def _insert_heading(page, runs, level):
    _open_toolbox(page)
    # Header toolbox items, in document order: [0]="Подзаголовок H2", [1]="Подзаголовок H3".
    idx = 0 if level <= 2 else 1
    page.eval_on_selector_all(
        '.ce-toolbox__item[data-type="header"]', f"els => els[{idx}].click()"
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


def _insert_list(page, list_block, is_last=False):
    _open_toolbox(page)
    page.eval_on_selector('.ce-toolbox__item[data-type="list"]', "el => el.click()")
    page.wait_for_selector(LIST_SEL, timeout=8000)
    # type items; Enter starts a new <li>. No trailing Enter after the last item yet.
    for idx, item in enumerate(list_block.items):
        if idx:
            page.keyboard.press("Enter")
        _type_runs(page, item.runs)
    # ordered? toggle via the block settings gear -> ORDERED_TUNE_LABEL tune.
    # CRITICAL: target the LAST list in the DOM (the one we just built). Earlier
    # lists also match LIST_SEL, and eval_on_selector picks the FIRST — which
    # would toggle the wrong list (swapping ordered/unordered between lists).
    if list_block.ordered:
        # open the settings gear of the LAST (current) list block
        gear_click = (
            "els => els[els.length - 1].closest('.ce-block')"
            f".querySelector('{SETTINGS_TOGGLER_SEL}').click()"
        )
        page.eval_on_selector_all(LIST_SEL, gear_click)
        page.wait_for_selector(BLOCK_SETTINGS_ITEM_SEL, timeout=5000)
        page.eval_on_selector_all(
            BLOCK_SETTINGS_ITEM_SEL,
            f"els => {{ const it = els.find(e => (e.innerText||'').includes('{ORDERED_TUNE_LABEL}')); if (it) it.click(); }}",
        )
        # confirm the modifier class applied on the last list, then close the
        # tune popover. NOTE: Escape here closes the whole VC editor modal —
        # instead click the settings gear again to toggle just the popover shut.
        page.wait_for_selector(LIST_ORDERED_SEL, timeout=5000)
        page.eval_on_selector_all(LIST_SEL, gear_click)
        # Re-focus the last <li> with a REAL click (not a JS selection): Editor.js
        # only repositions its toolbar on real caret events, so a JS focus would
        # leave the toolbar stale and the next block's "+" hidden. End puts the
        # caret at the line end so the exit double-Enter reliably leaves the block.
        page.locator(f"{LIST_ORDERED_SEL} li").last.click()
        page.keyboard.press("End")
    # exit the list into a fresh paragraph block below (double-Enter on empty item).
    # Skip when this is the last block, or we'd leave a trailing empty paragraph.
    if not is_last:
        page.keyboard.press("Enter")
        page.keyboard.press("Enter")
    time.sleep(0.3)


def _insert_quote(page, quote, is_last=False):
    _open_toolbox(page)
    page.eval_on_selector('.ce-toolbox__item[data-type="quote"]', "el => el.click()")
    # The empty body field has zero height until focused, so wait for it to be
    # ATTACHED (not "visible") and click with force to bypass the visibility check.
    page.wait_for_selector(QUOTE_BODY_SEL, state="attached", timeout=8000)
    page.locator(QUOTE_BODY_SEL).last.click(force=True)
    _type_runs(page, quote.runs)   # author field left empty
    # exit the quote into a fresh paragraph block below. The body is multiline,
    # so Enter there only adds a newline; instead focus the single-line author
    # field (left empty) and press Enter, which leaves the block. Skip when this
    # is the last block, or we'd leave a trailing empty paragraph.
    if not is_last:
        page.locator(QUOTE_AUTHOR_SEL).last.click(force=True)
        page.keyboard.press("Enter")
    time.sleep(0.3)


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
            _insert_heading(page, block.runs, block.level)
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
        elif isinstance(block, ListBlock):
            log(f"[{i}] list ordered={block.ordered} items={len(block.items)}")
            _insert_list(page, block, is_last=(i == last))
        elif isinstance(block, Quote):
            log(f"[{i}] quote ({len(block.runs)} runs)")
            _insert_quote(page, block, is_last=(i == last))
        # Enter creates the next empty block (needed for the next heading/image's
        # toolbox, and to leave an image's caption). Skip it after the last block
        # so we don't leave a trailing empty paragraph. List/Quote ALREADY exit
        # into a fresh paragraph below (double-Enter), so skip the generic Enter
        # for them or we'd leave an extra empty block.
        if i < last and not isinstance(block, (ListBlock, Quote)):
            page.keyboard.press("Enter")
        time.sleep(0.3)

    # Confirm the draft saved (URL gains an id=NNN).
    try:
        page.wait_for_function("() => location.href.includes('id=')", timeout=15000)
        log(f"Draft saved: {page.url}")
    except Exception:
        log(f"WARNING: did not detect saved-draft URL; current: {page.url}")

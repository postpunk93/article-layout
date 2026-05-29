# VC Paste-Based Layout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rework the VC adapter from per-block typing to one real-clipboard paste of the body, then restore images, quotes, and bold/italic in post-passes.

**Architecture:** Emit body HTML (quotes as `<p>`, images as `[[IMG:file]]` markers), put it on the real OS clipboard via an offscreen `contenteditable` + `execCommand('copy')`, and real `Ctrl+V` into the Editor.js body so the structure lands. Then, on the parsed block sequence (order preserved): re-apply `strong`/`em` by character-offset selection, replace quote paragraphs by deleting + inserting native quote blocks, and replace image markers with native uploads. See design: `docs/plans/2026-05-30-vc-paste-layout-design.md`.

**Tech Stack:** Python, Playwright (sync API), Editor.js DOM, pytest.

---

## Task 1: `emit_body` quote-as-paragraph mode

**Files:**
- Modify: `src/emit_html.py:18-48`
- Test: `tests/test_emit_html.py`

**Step 1: Write the failing test**

Add to `tests/test_emit_html.py`:

```python
def test_quote_as_paragraph_mode_renders_p():
    doc = Document(title="T", blocks=[Quote(runs=[Run("q < x", False, False)])])
    html = emit_body(doc, quote_as_paragraph=True)
    assert "<p>q &lt; x</p>" in html
    assert "<blockquote>" not in html


def test_quote_default_still_blockquote():
    doc = Document(title="T", blocks=[Quote(runs=[Run("q", False, False)])])
    assert "<blockquote>q</blockquote>" in emit_body(doc)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_emit_html.py::test_quote_as_paragraph_mode_renders_p -v`
Expected: FAIL — `emit_body() got an unexpected keyword argument 'quote_as_paragraph'`.

**Step 3: Write minimal implementation**

In `src/emit_html.py`, change the signature and the `Quote` branch:

```python
def emit_body(doc, caption_marker=True, quote_as_paragraph=False):
```

```python
        elif isinstance(b, Quote):
            tag = "p" if quote_as_paragraph else "blockquote"
            parts.append(f"<{tag}>{_runs_html(b.runs)}</{tag}>")
```

Update the docstring's caption sentence to also note: "Pass ``quote_as_paragraph=True`` (e.g. VC) to render quotes as ``<p>`` so they survive a lossy paste and are converted to quote blocks afterwards."

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_emit_html.py -v`
Expected: PASS (all, including the two new ones).

**Step 5: Commit**

```bash
git add src/emit_html.py tests/test_emit_html.py
git commit -m "feat(emit): quote_as_paragraph mode for VC paste"
```

---

## Task 2: `format_segments` pure helper (runs → offset ranges)

A pure function that turns a run list into the character ranges needing inline formatting. Lives in `vc_adapter` (module imports only `time`, `pathlib`, `src.ir`, `src.emit_html` — no Playwright at import time, so it is unit-testable).

**Files:**
- Modify: `src/vc_adapter.py` (add top-level function)
- Test: Create `tests/test_vc_format_segments.py`

**Step 1: Write the failing test**

Create `tests/test_vc_format_segments.py`:

```python
from src.ir import Run
from src.vc_adapter import format_segments


def test_no_formatting_returns_empty():
    runs = [Run("plain text", False, False)]
    assert format_segments(runs) == []


def test_bold_run_offsets():
    # "a " (0-2) then "bold" (2-6) bold then " end" (6-10)
    runs = [Run("a ", False, False), Run("bold", True, False), Run(" end", False, False)]
    assert format_segments(runs) == [(2, 6, True, False)]


def test_italic_and_bolditalic():
    runs = [Run("x", False, True), Run("y", True, True)]
    # "x" italic at 0-1; "y" bold+italic at 1-2
    assert format_segments(runs) == [(0, 1, False, True), (1, 2, True, True)]


def test_empty_run_skipped_but_advances_nothing():
    runs = [Run("", True, False), Run("hi", True, False)]
    assert format_segments(runs) == [(0, 2, True, False)]
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_vc_format_segments.py -v`
Expected: FAIL — `ImportError: cannot import name 'format_segments'`.

**Step 3: Write minimal implementation**

Add to `src/vc_adapter.py` (top level, after imports):

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_vc_format_segments.py -v`
Expected: PASS (all four).

**Step 5: Commit**

```bash
git add src/vc_adapter.py tests/test_vc_format_segments.py
git commit -m "feat(vc): format_segments helper (runs -> offset ranges)"
```

---

## Task 3: Clipboard paste + range-selection JS helpers

Browser interaction — not unit-tested. Implement, then verify in Task 6's run.

**Files:**
- Modify: `src/vc_adapter.py`

**Step 1: Add `_paste_via_clipboard`**

```python
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
    page.click(BODY_SEL_FALLBACK if False else TITLE_SEL)  # placeholder; replaced below
```

Then fix the focus/paste tail (replace the placeholder line) with:

```python
    page.locator(".codex-editor .ce-block").first.click()
    page.keyboard.press("Control+V")
    # Wait for the pasted blocks to materialise.
    try:
        page.wait_for_function(
            "(n) => document.querySelectorAll('.codex-editor .ce-block').length >= n",
            arg=expected_blocks,
            timeout=15000,
        )
    except Exception:
        pass
```

(There is no body contenteditable selector constant yet; the body root is
`.codex-editor` and blocks are `.ce-block` per `platform-notes.md`. Click the first
block to put the caret in the body before Ctrl+V.)

**Step 2: Add `_select_range` (char offsets within a block element)**

```python
def _select_range(page, container_selector, start, end):
    """Select [start, end) chars within the element matched by container_selector.

    Walks the element's text nodes by cumulative length to build a DOM Range, then
    sets it as the window selection so a following Ctrl+B/Ctrl+I formats it.
    """
    page.evaluate(
        """({sel, start, end}) => {
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
```

**Step 3: Commit**

```bash
git add src/vc_adapter.py
git commit -m "feat(vc): clipboard-paste and range-select helpers"
```

---

## Task 4: Rewrite `build_document` — paste + post-passes

Replaces the per-block body loop. Keep `_type_runs`, `_open_toolbox`, `_insert_quote`, `_insert_image` (or its upload-wait) as reusable helpers; remove the old block dispatch loop.

**Files:**
- Modify: `src/vc_adapter.py:172-219` (`build_document`)

**Step 1: New `build_document` body**

```python
def build_document(page, doc, images_dir: Path, log=print):
    log(f"Opening editor: {EDITOR_URL}")
    page.goto(EDITOR_URL)
    page.wait_for_selector(TITLE_SEL, timeout=30000)
    time.sleep(2)

    log(f"Title: {doc.title!r}")
    page.click(TITLE_SEL)
    page.keyboard.type(doc.title)
    page.keyboard.press("Enter")  # creates the first body block
    time.sleep(0.5)

    # 1. Paste the whole structure (quotes as <p>, images as [[IMG:file]] markers).
    body_html = emit_body(doc, caption_marker=False, quote_as_paragraph=True)
    log("Pasting body via real clipboard…")
    _paste_via_clipboard(page, body_html, expected_blocks=len(doc.blocks))
    time.sleep(0.8)

    # 2. Validate mapping. On mismatch, skip positional passes (still do images).
    n_blocks = page.evaluate(
        "() => document.querySelectorAll('.codex-editor .ce-block').length"
    )
    positional_ok = n_blocks == len(doc.blocks)
    if not positional_ok:
        log(f"WARNING: block mapping off (expected {len(doc.blocks)}, got {n_blocks}); "
            f"skipping strong/em + quote passes — fix those by hand.")

    block_sel = ".codex-editor .ce-block:nth-of-type({})"  # 1-based in :nth-of-type

    # 3a. strong/em for non-reinserted blocks (paragraph/heading/list).
    if positional_ok:
        for i, block in enumerate(doc.blocks):
            if isinstance(block, (Heading, Paragraph)):
                for (s, e, b, it) in format_segments(block.runs):
                    _select_range(page, block_sel.format(i + 1) + " [contenteditable]", s, e)
                    if b:  page.keyboard.press("Control+b")
                    if it: page.keyboard.press("Control+i")
            elif isinstance(block, ListBlock):
                _format_list_items(page, i + 1, block)

    # 3b. quotes: delete the paragraph at the index, insert a native quote block.
    if positional_ok:
        for i, block in enumerate(doc.blocks):
            if isinstance(block, Quote):
                log(f"[{i}] quote -> convert paragraph to quote block")
                _replace_paragraph_with_quote(page, i + 1, block)

    # 4. images last (block count changes); match markers by content.
    images = [b for b in doc.blocks if isinstance(b, Image)]
    log(f"Uploading {len(images)} image(s)…")
    for block in images:
        path = images_dir / block.file
        if not path.exists():
            log(f"  IMAGE MISSING ON DISK: {path} — leaving marker [[IMG:{block.file}]]")
            continue
        _replace_marker_with_image(page, block, path, log)

    # 5. Confirm the draft saved.
    try:
        page.wait_for_function("() => location.href.includes('id=')", timeout=15000)
        log(f"Draft saved: {page.url}")
    except Exception:
        log(f"WARNING: did not detect saved-draft URL; current: {page.url}")
```

**Step 2: Add `_format_list_items`**

```python
def _format_list_items(page, nth_block, list_block):
    """Apply strong/em inside each <li> of the pasted list block (per-item offsets)."""
    base = f".codex-editor .ce-block:nth-of-type({nth_block}) li"
    for k, item in enumerate(list_block.items):
        segs = format_segments(item.runs)
        for (s, e, b, it) in segs:
            page.evaluate(
                """({base, k, start, end}) => {
                    const li = document.querySelectorAll(base)[k];
                    if (!li) return false;
                    const w = document.createTreeWalker(li, NodeFilter.SHOW_TEXT);
                    let node, acc = 0, range = document.createRange(), set = false;
                    while ((node = w.nextNode())) {
                        const len = node.textContent.length;
                        if (!set && acc + len >= start) { range.setStart(node, start-acc); set = true; }
                        if (set && acc + len >= end) {
                            range.setEnd(node, end-acc);
                            const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
                            return true;
                        }
                        acc += len;
                    }
                    return false;
                }""",
                {"base": base, "k": k, "start": s, "end": e},
            )
            if b:  page.keyboard.press("Control+b")
            if it: page.keyboard.press("Control+i")
```

**Step 3: Add `_replace_paragraph_with_quote`**

```python
def _replace_paragraph_with_quote(page, nth_block, quote):
    """Empty the paragraph at nth_block, then insert a native quote block in place.

    The editor cannot convert a paragraph to a quote, so we clear the paragraph
    (Ctrl+A, Delete) and build a quote block on the now-empty active block, typing
    the runs (which carries bold/italic inline). Net block count is unchanged.
    """
    page.locator(f".codex-editor .ce-block:nth-of-type({nth_block}) [contenteditable]").first.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    _open_toolbox(page)
    page.eval_on_selector('.ce-toolbox__item[data-type="quote"]', "el => el.click()")
    page.wait_for_selector(QUOTE_BODY_SEL, state="attached", timeout=8000)
    page.locator(QUOTE_BODY_SEL).last.click(force=True)
    _type_runs(page, quote.runs)
```

**Step 4: Add `_replace_marker_with_image`**

Reuse the existing upload-wait + caption logic from the old `_insert_image`, but locate the marker paragraph first and remove it after.

```python
def _replace_marker_with_image(page, block, path, log):
    """Find the [[IMG:file]] marker paragraph, make it active, upload natively, caption it."""
    needle = f"[[IMG:{block.file}]]"
    found = page.evaluate(
        """(needle) => {
            const blocks = [...document.querySelectorAll('.codex-editor .ce-block')];
            const b = blocks.find(el => (el.innerText || '').includes(needle));
            if (!b) return false;
            const ed = b.querySelector('[contenteditable]');
            if (!ed) return false;
            const range = document.createRange();
            range.selectNodeContents(ed);
            const s = window.getSelection(); s.removeAllRanges(); s.addRange(range);
            ed.focus();
            return true;
        }""",
        needle,
    )
    if not found:
        log(f"  marker {needle} not found — skipping")
        return
    page.keyboard.press("Delete")  # empty the marker paragraph -> active empty block
    log(f"  image: {block.file} caption={'yes' if block.caption else 'no'}")
    _insert_image(page, path, block.caption)  # existing toolbox->media->upload->caption
```

(Keep the existing `_insert_image`'s async upload `wait_for_function` and caption
typing unchanged.)

**Step 5: Remove the old per-block loop**

Delete the old `for i, block in enumerate(doc.blocks): if isinstance(... )` body loop and its trailing `Enter`/`time.sleep` logic now superseded by the paste flow. Keep `_insert_list`, `_insert_quote` only if still referenced; otherwise delete `_insert_list` (lists now arrive via paste) and keep `_insert_quote` logic folded into `_replace_paragraph_with_quote` (remove `_insert_quote` if unused).

**Step 6: Sanity import + existing tests**

Run: `python -m pytest tests/ -v`
Expected: PASS (parser/IR/emit/orchestrator/format_segments). No browser tests run here.

**Step 7: Commit**

```bash
git add src/vc_adapter.py
git commit -m "feat(vc): paste-based build_document with strong/em, quote, image passes"
```

---

## Task 5: Prune stale docs note

**Files:**
- Modify: `docs/platform-notes.md` (the "Body approach — per-block typing (paste is lossy)" section)

**Step 1:** Replace that section's text to record the real-vs-synthetic paste finding: real `Ctrl+V` from the OS clipboard keeps paragraphs/headings/lists; `strong`/`em`, quotes, and images are restored afterward (offset re-format; delete+insert quote block; native image upload by marker). Keep the selector tables intact.

**Step 2: Commit**

```bash
git add docs/platform-notes.md
git commit -m "docs: VC body approach is now real-clipboard paste + restore passes"
```

---

## Task 6: End-to-end validation (manual)

No automated browser tests — validate like the Pikabu adapter was.

**Step 1:** Ensure a logged-in VC profile exists: `python cli.py status` (and `python cli.py login <client> vc` if needed).

**Step 2:** Run layout on a quote/list/image-rich fixture:

Run: `python cli.py layout <client> vc in/lists-quotes`
(Adjust to the real CLI arg shape; confirm with `python cli.py layout --help` or `cli.py`.)

**Step 3:** In the opened browser draft, verify by eye:
- Paragraphs, H2/H3, bullet + ordered lists are correct and in order.
- `strong`/`em` landed on the right words.
- Quotes are real quote blocks with correct text.
- Images uploaded at the right spots with captions; no leftover `[[IMG:…]]` markers.
- Draft saved (URL has `id=`); nothing published.

**Step 4:** Repeat on `in/chernika`. Note any block-mapping warnings in the log; if the count check fails, inspect whether paste split/merged a block and adjust `emit_body`/paste accordingly.

**Step 5:** If issues found, fix in `vc_adapter.py`, re-run. When clean, commit any fixes:

```bash
git add src/vc_adapter.py
git commit -m "fix(vc): paste-layout adjustments from e2e validation"
```

---

## Notes for the implementer

- **Selectors:** body root `.codex-editor`, blocks `.ce-block`, paragraph editable
  `.editor-text-tool` (a `[contenteditable]` inside the block), header tool, list
  `.editor-list-tool`, quote body `QUOTE_BODY_SEL` — all in `src/vc_adapter.py` /
  `docs/platform-notes.md`. Prefer `[contenteditable]` within a block when a generic
  editable target is needed.
- **`:nth-of-type` vs `.ce-block`:** if `.ce-block` are not direct siblings of the
  same type, switch the positional selector to indexing
  `document.querySelectorAll('.codex-editor .ce-block')[i]` inside `page.evaluate`
  rather than CSS `:nth-of-type`. Verify on the first run.
- **Clipboard fallback:** if `execCommand('copy')` + `Ctrl+V` drops structure, switch
  `_paste_via_clipboard` to `context.grant_permissions(["clipboard-write"])` +
  `navigator.clipboard.write([new ClipboardItem({...})])`. Both are cheap.
- **Never publish.** Stop at a saved draft (`id=` in URL).
```

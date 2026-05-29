# VC paste-based layout — design

**Date:** 2026-05-30
**Status:** approved (brainstorming)
**Topic:** Rework the VC adapter from per-block typing to a single high-fidelity
clipboard paste (Pikabu-style), then restore what paste drops.

## Problem

The current `vc_adapter.build_document` builds the body **block by block**: empty
block → toolbox "+" → pick item by type → type runs, plus gear-toggles for ordered
lists and multi-step exits from lists/quotes. It is slow and fragile (stale toolbars,
"+" not-visible fallbacks, ordered-list gear targeting the wrong block).

The Pikabu adapter is much simpler: paste the whole body HTML once, then replace
image markers. We want the same shape for VC.

## Key finding

`platform-notes.md` recorded "paste is lossy" for VC — but that was a **synthetic**
`ClipboardEvent` (as used for Pikabu's Tiptap). A **real** `Ctrl+V` from the OS
clipboard behaves differently: Editor.js processes it like a manual paste.

Confirmed by the user's manual experience pasting from the Google Doc into VC:

- **Survives paste:** paragraphs, subheadings (H2/H3), bullet/ordered lists.
- **Lost on paste:** images, quotes, `strong`/`em` (inline bold/italic).

So the plan is: paste structure via a real clipboard paste, then restore images,
quotes, and inline formatting in post-passes.

Editor-specific constraint (user): **a paragraph cannot be converted to a quote**
in this editor. A quote must be made by deleting the paragraph and inserting a fresh
quote block in its place, then typing the text.

## Approach (chosen: A, implemented incrementally)

Rewrite `build_document` wholesale (as was done for Pikabu), salvaging reusable
pieces (async image-upload wait; `_type_runs`; quote insertion). Flow:

```
1. goto editor → type title → Enter into body
2. body_html = emit_body(doc, caption_marker=False, quote_as_paragraph=True)
   headings, paragraphs, lists; quotes → plain <p>; images → [[IMG:file]] markers
3. Put HTML on the REAL clipboard and paste:
   offscreen contenteditable → innerHTML=html → select → execCommand('copy')
   → click(body) → Ctrl+V        (real paste; Editor.js takes the structure)
4. Validate mapping: count(.ce-block) == len(doc.blocks)
5. Positional post-passes (paste preserves block order; these keep block count):
   5a. strong/em — paragraphs / headings / lists with formatted runs
   5b. quotes    — delete paragraph at index, insert quote block, type runs
6. Images last (block count changes here): replace each [[IMG:file]] marker by
   content with a native VC upload + caption
7. Wait for id= in URL → draft saved
```

### Why these decisions

- **Real clipboard via `execCommand('copy')` from an offscreen `contenteditable`**,
  not `navigator.clipboard.write` — needs no permissions/user gesture and mimics a
  manual copy from a page. Fallback if it misbehaves: `grant_permissions(["clipboard
  -write"])` + `navigator.clipboard.write(ClipboardItem)`. Decided empirically on the
  first run; both are cheap.
- **Quotes emitted as `<p>`** (not `<blockquote>`) so the text reliably lands as a
  paragraph and the 1:1 mapping holds; converted to quote blocks later.
- **Text passes (5a/5b) before images (6)** so positional work runs on a stable block
  count; images are then matched by marker content, not index.

## Components

### `emit_html.py`

Add `quote_as_paragraph=False` to `emit_body`. When `True` (VC mode), `Quote`
renders as `<p>…</p>` instead of `<blockquote>`. VC calls with
`caption_marker=False, quote_as_paragraph=True`. `strong`/`em` stay in the HTML
(harmless; Editor.js strips them anyway — offsets are recomputed from the IR, not
read back from the DOM).

```python
def emit_body(doc, caption_marker=True, quote_as_paragraph=False):
    ...
    elif isinstance(b, Quote):
        tag = "p" if quote_as_paragraph else "blockquote"
        parts.append(f"<{tag}>{_runs_html(b.runs)}</{tag}>")
```

### `vc_adapter.py`

**`_paste_via_clipboard(page, html)`** — offscreen `contenteditable`, set
`innerHTML`, select contents, `document.execCommand('copy')`, remove element; then
`click(BODY_SEL)` + `keyboard.press("Control+V")`. Wait until `.ce-block` count
reaches the expected number.

**Mapping validation** — compare `count(.ce-block)` to `len(doc.blocks)`. Match →
run 5a/5b by index. Mismatch → log `expected N, got M`, **skip 5a/5b**, still run
images (matched by marker content). Structure is preserved either way.

**5a. `_apply_runs_formatting(page, block_index, runs)`** — walk runs accumulating a
char offset; for each run with bold/italic, select its `[start, end)` range inside the
block's editable element and press Ctrl+B / Ctrl+I. Helper `_select_range` walks the
block's text nodes by cumulative length to build a DOM `Range`. Lists: handle
per-`<li>` (find the k-th item, apply offsets within it). Only for non-reinserted
blocks (paragraphs/headings/lists).

**5b. quotes (delete + insert by index)** — for each `Quote` in IR at its block
index: real click into that block → `Ctrl+A` → `Delete` (empty the paragraph) → on the
now-empty active block open "+" → quote item → `_type_runs(quote.runs)`. `_type_runs`
applies bold/italic inline, so quotes need no separate 5a pass. Net block count
unchanged → other quote indices stay valid.

**6. images (last)** — like Pikabu but native upload (VC strips `<img>`/data-URI):
for each `Image` in order, find the `[[IMG:file]]` marker paragraph by content, make
it active, open "+" → media → file chooser → `set_files`, reuse the existing
`wait_for_function` for a real `https` src, type caption into the image block's native
caption field (`.editor-tool-input--text-sm`, `.last`), delete the leftover marker
paragraph.

## Error handling

- **Image missing on disk** → log + skip; leave the marker visible in the body (as
  Pikabu does).
- **Async upload** → reuse the existing `wait_for_function` on a real `https` src.
- **Mapping mismatch** → log, skip 5a/5b, still do images; user fixes formatting and
  quotes by hand.
- **Clipboard fallback** → `navigator.clipboard.write` if `execCommand('copy')`+Ctrl+V
  drops structure.
- **Draft save** → wait for `id=` in URL; never publish.

## Testing

- Unit: `emit_body(quote_as_paragraph=True)` renders quotes as `<p>` and images as
  `[[IMG:file]]` markers.
- Unit: the runs → offset-segment computation (pure Python helper) — no browser.
- End-to-end (manual, as for Pikabu): run on fixtures `in/chernika` and
  `in/lists-quotes` to a saved draft; eyeball structure, images, captions, quotes,
  bold/italic.
- Existing parser / IR / orchestrator tests are unaffected.

## Out of scope / deferred

- Links (`<a>`) inline formatting — not currently in the IR runs path here.
- Automatic verification of paste fidelity beyond the block-count check.

# Habr Adapter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a third platform adapter that lays out a GDoc-sourced article into Habr's visual editor (title + body + images + captions), then stops on the article-settings screen — never publishes.

**Architecture:** Mirror the existing adapter contract (`build_document(page, doc, images_dir)` + module constants, registered in `sessions.PLATFORMS`). Habr's paste is high-fidelity (Pikabu model: one paste for the whole body), so the only post-passes are quotes and captions; image transport is settled by a one-off discovery probe. Habr supports a single subheading level, so `emit_html` degrades h3+ to a bold-line paragraph.

**Tech Stack:** Python 3.10, Playwright (sync), pytest. No pytest config — run from repo root, imports are `from src.X import Y`.

Design doc: `docs/plans/2026-05-31-habr-adapter-design.md`. Read it before starting.

---

## Conventions (read once)

- Run tests from the repo root: `python -m pytest <path> -v`.
- Adapters are modules in `src/` exporting an `EDITOR_URL`-style constant, selector
  constants, and `build_document(page, doc, images_dir)`. See `src/pikabu_adapter.py`
  (high-fidelity paste + marker-replace images + native captions) and
  `src/vc_adapter.py` (lossy paste + restore passes, block-count gate) as the two
  reference adapters. Habr is closest to Pikabu.
- IR types are in `src/ir.py`: `Document(title, blocks)`, `Heading(level, runs)`,
  `Paragraph(runs)`, `Image(file, caption)`, `ListBlock(ordered, items)`,
  `ListItem(runs)`, `Quote(runs)`, `Run(text, bold, italic)`.
- Selectors: stable `data-test`/attributes only; never css-module hash suffixes
  (they drift between deploys). See the warning in `docs/platform-notes.md`.
- Commit after every green step. Branch is `feat/habr-adapter` (already created).

---

## Task 1: `emit_html` heading degradation (h3+ → bold line)

Pure logic, no browser. Habr has one subheading level (h2). `Heading(level>=3)` must
render as `<p><strong>…</strong></p>`, not `<h3>`. Gate behind a new
`max_heading_level` param so VC/Pikabu behavior is unchanged (default = no limit).

**Files:**
- Modify: `src/emit_html.py`
- Test: `tests/test_emit_html.py`

**Step 1: Write the failing test**

Add to `tests/test_emit_html.py`:

```python
def test_max_heading_level_degrades_h3_to_bold_paragraph():
    doc = Document(
        title="T",
        blocks=[
            Heading(level=2, runs=[Run("Sub", False, False)]),
            Heading(level=3, runs=[Run("Deep", False, False)]),
        ],
    )
    html = emit_body(doc, max_heading_level=2)
    assert "<h2>Sub</h2>" in html
    assert "<h3>" not in html
    assert "<p><strong>Deep</strong></p>" in html


def test_max_heading_level_default_keeps_h3():
    doc = Document(title="T", blocks=[Heading(level=3, runs=[Run("Deep", False, False)])])
    html = emit_body(doc)  # no max_heading_level -> unchanged behavior
    assert "<h3>Deep</h3>" in html


def test_max_heading_level_preserves_inline_styles_in_degraded_heading():
    doc = Document(
        title="T",
        blocks=[Heading(level=3, runs=[Run("a ", False, False), Run("b", False, True)])],
    )
    html = emit_body(doc, max_heading_level=2)
    # degraded heading is a bold paragraph; original italics survive nested
    assert "<p><strong>a <em>b</em></strong></p>" in html
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_emit_html.py::test_max_heading_level_degrades_h3_to_bold_paragraph -v`
Expected: FAIL — `emit_body() got an unexpected keyword argument 'max_heading_level'`.

**Step 3: Write minimal implementation**

In `src/emit_html.py`, add the param and the degradation branch. Signature becomes:

```python
def emit_body(doc, caption_marker=True, quote_as_paragraph=False, img_sep=":",
              max_heading_level=None):
```

In the `isinstance(b, Heading)` branch, replace the single append with:

```python
        if isinstance(b, Heading):
            if max_heading_level is not None and b.level > max_heading_level:
                # Habr has one subheading level: a deeper heading degrades to a
                # bold line (keep any inner italics) rather than an <hN> tag.
                parts.append(f"<p><strong>{_runs_html(b.runs)}</strong></p>")
            else:
                parts.append(f"<h{b.level}>{_runs_html(b.runs)}</h{b.level}>")
```

Update the docstring with a sentence describing `max_heading_level`.

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_emit_html.py -v`
Expected: all PASS (new tests + existing ones unchanged).

**Step 5: Commit**

```bash
git add src/emit_html.py tests/test_emit_html.py
git commit -m "feat(emit): max_heading_level degrades deep headings to a bold line"
```

---

## Task 2: Discovery probe on the Habr sandbox

Resolve every Habr-specific unknown BEFORE writing browser code. This is manual
investigation, not TDD. Produces (a) a filled "Habr" section in
`docs/platform-notes.md` and (b) concrete values for the adapter constants used in
Task 3+.

**Prerequisite:** a logged-in sandbox profile. Run yourself:
`! python cli.py login <client> habr` — but `habr` is not registered yet, so for the
probe, log in with a throwaway script that opens a persistent context on
`.profiles/<client>/habr/` and navigates to the sandbox editor, exactly like the
onboarding pattern step 1 in `docs/platform-notes.md`.

**Files:**
- Create (throwaway, deleted at end of task): `src/_discover_habr.py`
- Modify: `docs/platform-notes.md` (append a "Habr" section)

**Step 1: Seed the profile and open the editor**

Write `src/_discover_habr.py` that launches a visible persistent context on
`.profiles/<client>/habr/` (copy the launch args from `sessions.open_context`) and
navigates to the Habr sandbox article editor. Find and record the exact editor URL.

**Step 2: Answer the six discovery questions**

Drive the probe (and DevTools by hand) to record, for the "Habr" notes section:

1. **Navigation & auth** — exact sandbox editor URL; a logged-in-only selector
   (alive-marker candidate); whether the draft autosaves and how that shows.
2. **Editor engine & selectors** — framework (ProseMirror / contenteditable / other);
   the title (h1) field selector and the body container selector; which attributes
   are stable (`data-test`) vs hashed.
3. **Fidelity of OUR HTML** — paste a sample built from `emit_body` (NOT copied from a
   GDoc) covering h2, paragraphs, bold/italic, ul/ol, and a quote; record which node
   tags/classes result and what (if anything) is lost.
4. **Image transport** — paste `<img src=data-URI>` and `<img src=https…>`; does Habr
   upload to habrastorage itself (wait for an `https` src) or strip it? Record the
   answer and, if it uploads, the final src host pattern and how to wait for it.
5. **Quote block & caption field** — the native quote block structure + how to create
   one from a selection/paragraph; whether an image has a native caption field and its
   selector.
6. **Stop point** — the button/text that moves «черновик → настройка статьи», and a
   marker selector that uniquely identifies the settings screen (success signal).

**Step 3: Record findings**

Append a "Habr" section to `docs/platform-notes.md` with: editor URL, engine, title
+ body selectors, alive-marker, paste mechanism that worked, image-transport verdict
(+ wait condition), quote mechanism, caption-field selector (or "none"), settings
button + settings-screen marker. Keep it terse and selector-focused, like the VC and
Pikabu sections.

**Step 4: Delete the throwaway probe**

```bash
git rm -f src/_discover_habr.py 2>/dev/null || rm -f src/_discover_habr.py
```

**Step 5: Commit**

```bash
git add docs/platform-notes.md
git commit -m "docs: record Habr editor discovery (selectors + paste/image/quote/caption/stop)"
```

> The remaining tasks reference these findings as **[D:<n>]** (discovery item n).
> Substitute the real selectors/URLs you recorded.

---

## Task 3: Adapter skeleton + registration

Create the module with constants from Task 2 and a `build_document` that, for now,
only opens the editor and types the title. Register it so `cli.py login/status/layout`
see `habr`.

**Files:**
- Create: `src/habr_adapter.py`
- Modify: `src/sessions.py` (import + `PLATFORMS` entry)
- Test: `tests/test_sessions_registry.py`

**Step 1: Write the failing test**

Read `tests/test_sessions_registry.py` first to match its style, then add:

```python
def test_habr_registered_with_contract():
    entry = sessions.PLATFORMS["habr"]
    assert callable(entry["build_document"])
    assert entry["editor_url"]
    assert entry["alive_marker"]
    assert "habr" in sessions.known_platforms()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sessions_registry.py::test_habr_registered_with_contract -v`
Expected: FAIL — `KeyError: 'habr'`.

**Step 3: Write minimal implementation**

Create `src/habr_adapter.py` (substitute **[D:*]** values from Task 2):

```python
"""Drive Habr's visual article editor to build a draft from a Document.

Habr's editor accepts HIGH-FIDELITY HTML paste (Pikabu model: the whole body goes
in one paste — headings, paragraphs, bold/italic, lists survive). Habr has a SINGLE
subheading level, so the body is emitted with max_heading_level=2 (h3+ -> bold line).

Post-passes: convert pasted quotes to native quote blocks, and move image captions
from body paragraphs into the image's native caption field. Image transport is per
the discovery probe (see docs/platform-notes.md "Habr").

Visible browser, persistent profile. STOPS on the article-settings screen after
clicking "Далее в настройки" — never publishes.
"""
from pathlib import Path

from src.emit_html import emit_body

EDITOR_URL = "[D:1 sandbox editor URL]"
TITLE_SEL = "[D:2 title field selector]"
BODY_SEL = "[D:2 body container selector]"
# Visible only to a logged-in user -> used as the liveness marker.
ALIVE_SEL = TITLE_SEL


def build_document(page, doc, images_dir):
    page.goto(EDITOR_URL, wait_until="domcontentloaded")
    page.wait_for_selector(BODY_SEL)
    page.click(TITLE_SEL)
    page.type(TITLE_SEL, doc.title)
```

In `src/sessions.py`, add to the import line:

```python
from src import vc_adapter, pikabu_adapter, habr_adapter
```

and add a `PLATFORMS` entry:

```python
    "habr": {
        "build_document": habr_adapter.build_document,
        "editor_url": habr_adapter.EDITOR_URL,
        "alive_marker": habr_adapter.ALIVE_SEL,
    },
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sessions_registry.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/habr_adapter.py src/sessions.py tests/test_sessions_registry.py
git commit -m "feat(habr): adapter skeleton + registration (title + open editor)"
```

---

## Task 4: Body paste (one high-fidelity paste)

Paste the whole body in one shot, using the mechanism Task 2 confirmed works (a
synthetic `ClipboardEvent` with `text/html`, like Pikabu, or the real OS clipboard,
like VC). Body HTML comes from `emit_body(doc, max_heading_level=2, …)`.

**Files:**
- Modify: `src/habr_adapter.py`

**Step 1: Add the paste helper and wire it into `build_document`**

Add `_paste_html(page, html)` modeled on `src/pikabu_adapter.py:_paste_html` (or the
VC real-clipboard sequence if **[D:3]** showed the synthetic event under-segments —
follow whichever the probe proved). Then after typing the title:

```python
    html = emit_body(doc, caption_marker=True, max_heading_level=2)
    _paste_html(page, html)
    page.wait_for_timeout(500)  # let the editor segment the paste into blocks
```

Choose `caption_marker` / `quote_as_paragraph` / `img_sep` to match what Task 2
proved pastes cleanly (e.g. VC needed `img_sep=" "` to avoid a `scheme:path` abort —
verify Habr's behavior and pick accordingly; record the choice in a code comment).

**Step 2: Manual smoke check**

Run: `! python cli.py layout <slug> <client> habr`
Expected: title set; body blocks (h2, paragraphs, bold/italic, lists) appear in the
editor. Images/quotes/captions are not handled yet — that's fine.

**Step 3: Commit**

```bash
git add src/habr_adapter.py
git commit -m "feat(habr): one high-fidelity body paste (emit max_heading_level=2)"
```

---

## Task 5: Image pass

Branch on the Task 2 image-transport verdict.

- **If Habr uploads images straight from pasted HTML:** emit `<img>` in the body and
  only WAIT for every image to acquire an `https` (habrastorage) src before
  continuing. No marker replacement.
- **If Habr strips images:** keep `[[IMG…]]` markers in the body and replace each in
  place by uploading the real file — paste a real `File` built from the local bytes
  (model `src/pikabu_adapter.py` image flow) or use the file chooser, then WAIT for
  the final `https` src (async upload).

**Files:**
- Modify: `src/habr_adapter.py`
- Test: `tests/test_habr_images.py` (only for the pure marker-matching helper, if the
  fallback path is used)

**Step 1 (fallback path only): TDD the marker-matching helper**

If using marker replacement, factor the "find images in IR order" logic into a pure
helper and test it:

```python
# tests/test_habr_images.py
from src.ir import Document, Image, Paragraph, Run
from src.habr_adapter import image_files_in_order

def test_image_files_in_order():
    doc = Document(title="T", blocks=[
        Paragraph(runs=[Run("x", False, False)]),
        Image(file="image2.png", caption=None),
        Image(file="image5.png", caption=[Run("c", False, False)]),
    ])
    assert image_files_in_order(doc) == ["image2.png", "image5.png"]
```

Run: `python -m pytest tests/test_habr_images.py -v` → FAIL, then implement
`image_files_in_order(doc)` in `src/habr_adapter.py`, then PASS.

**Step 2: Implement the image pass in `build_document`**

Implement the chosen path. For each image, after upload, assert via
`wait_for_function` that a new `<img>` has a real `https` src
(`complete && naturalWidth>0`) — skipping this scrambles block order in image-dense
regions (lesson from VC/Pikabu). Make each image best-effort: wrap in try/except,
log a warning, continue.

**Step 3: Manual smoke check**

Run: `! python cli.py layout <slug> <client> habr`
Expected: every image present with a habrastorage `https` src; block order intact.

**Step 4: Commit**

```bash
git add src/habr_adapter.py tests/test_habr_images.py
git commit -m "feat(habr): image pass (upload + wait for https src)"
```

---

## Task 6: Quote pass

Paste does not turn a paragraph into a quote. Convert each quote to Habr's native
quote block using the mechanism from **[D:5]** (toolbar button on a selection, or
empty-the-paragraph + insert a native quote block, à la VC).

**Files:**
- Modify: `src/habr_adapter.py`

**Step 1: Add a block-count reconciliation gate**

Before the quote pass, compare the body block count (engine-specific selector from
**[D:2]**, excluding the title block if it lives in the same container) to
`len(doc.blocks)` minus any blocks that paste merges. On mismatch, log a warning and
SKIP the quote pass (mirror VC's gate). Record the exact counting rule in a comment.

**Step 2: Implement the quote conversion**

Walk the IR quotes; for each, locate its paragraph in the body (by text, like VC's
range select) and convert it to a native quote block. Best-effort per quote:
try/except, log, continue.

**Step 3: Manual smoke check**

Run: `! python cli.py layout <slug> <client> habr`
Expected: quotes render as native Habr quote blocks; non-quote text unchanged.

**Step 4: Commit**

```bash
git add src/habr_adapter.py
git commit -m "feat(habr): convert pasted quotes to native quote blocks"
```

---

## Task 7: Caption pass

Move each image's caption from the body paragraph under it into the image's native
caption field (**[D:5]** caption selector). Delete the leftover caption paragraph.

**Files:**
- Modify: `src/habr_adapter.py`
- Test: `tests/test_habr_captions.py` (pure caption-text helper, if one is factored)

**Step 1 (if a pure helper exists): TDD it**

If you factor caption extraction (e.g. `caption_text(image)` joining runs), add a
small unit test mirroring `tests/test_vc_format_segments.py` style.

**Step 2: Implement the caption pass**

For each image with a caption: write the caption text into the image's native caption
field (scroll the field into view, real click, type — the Pikabu lesson: a DOM Range
doesn't reliably sync), then remove the original `[[CAP…]]`/caption paragraph from the
body. Best-effort per caption: try/except, log, continue. If **[D:5]** found NO native
caption field, instead leave the caption paragraph in place and log it once.

**Step 3: Manual smoke check**

Run: `! python cli.py layout <slug> <client> habr`
Expected: captions sit in image caption fields; no stray caption paragraphs remain.

**Step 4: Commit**

```bash
git add src/habr_adapter.py tests/test_habr_captions.py
git commit -m "feat(habr): move captions into native image caption fields"
```

---

## Task 8: Navigate to settings and stop

Final action of `build_document`: click «Далее в настройки» (**[D:6]**) and confirm
arrival on the settings screen. Fill nothing; never publish.

**Files:**
- Modify: `src/habr_adapter.py`

**Step 1: Implement the navigation + stop**

After the caption pass:

```python
    page.click("[D:6 next-to-settings button selector or get_by_text]")
    page.wait_for_selector("[D:6 settings-screen marker selector]")
    # Stop here. cmd_layout leaves the window open for manual completion of
    # hubs / audience / keywords. We never fill settings and never publish.
```

**Step 2: Manual end-of-flow check**

Run: `! python cli.py layout <slug> <client> habr`
Expected: after the body is laid out, the editor advances to the settings screen and
the run returns (window left open by `cmd_layout`).

**Step 3: Commit**

```bash
git add src/habr_adapter.py
git commit -m "feat(habr): advance to settings screen and stop (no publish)"
```

---

## Task 9: End-to-end validation + record

Validate the whole adapter on a real article and record the result, like VC/Pikabu.

**Files:**
- Modify: `docs/platform-notes.md` (mark the Habr section "validated end-to-end")
- Modify: memory `MEMORY.md` + a new `project_habr_adapter.md` pointer (optional,
  matching the VC/Pikabu memory entries)

**Step 1: Full run on a representative article**

Pick an `in/<slug>` that has lists, quotes, images with captions, and at least one
h3. Run: `! python cli.py layout <slug> <client> habr`.

**Acceptance criteria (all must hold):**
- Title set; body blocks present and in order.
- h3 from the source rendered as a bold line (not a heading).
- Every image uploaded to habrastorage (`https` src); block order intact.
- Quotes are native quote blocks.
- Captions are in the images' native caption fields; no stray caption paragraphs.
- Run stops on the settings screen; nothing published.

**Step 2: Run the full unit suite**

Run: `python -m pytest -v`
Expected: all PASS (emit, registry, any habr helpers).

**Step 3: Record + commit**

Update the Habr notes section to "validated end-to-end on `in/<slug>` (<n> blocks,
<q> quotes, <i> images)". Add a memory pointer if matching the VC/Pikabu pattern.

```bash
git add docs/platform-notes.md
git commit -m "docs: Habr adapter validated end-to-end"
```

---

## Task 10: Finish the branch

Use superpowers:finishing-a-development-branch to decide merge vs PR vs cleanup,
following the project pattern (VC/Pikabu were merged to `main`).

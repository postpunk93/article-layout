# WordPress / Gutenberg adapter (ruminlab.ru) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Lay out a parsed GDoc `Document` as a saved **draft** in our WordPress
site (ruminlab.ru, Gutenberg), as one more platform in the unified one-window flow.

**Architecture:** One real `Ctrl+V` of clean body HTML produces native Gutenberg
blocks (headings/lists/quote/bold/italic), and `<img>` data-URIs auto-sideload to
the media library on paste. Title, image captions, and "save draft" are driven via
the top-window `wp.data` store (the editor canvas is in an iframe, but `wp.data`
lives on the top window). Recon-validated — see `recon_wp.py` and
`docs/plans/2026-06-02-wp-adapter-design.md`.

**Tech Stack:** Python, Playwright (Chrome via `channel="chrome"`), pytest. Reuses
`src/emit_html.emit_body`, the `src.sessions` profile/registry, and the
`Heading/Paragraph/Image/ListBlock/Quote` IR.

**Branch:** `feat/wp-adapter` (already created; the design doc is committed there).

---

## Background the executor must know

- **No-publish rule is absolute** (`docs/platform-notes.md` top): every adapter
  stops at a saved draft and leaves the window open; a human publishes. Never click
  "Опубликовать"; never call `savePost` with a publish status.
- **Adapter contract** (see any `src/*_adapter.py` + `src/sessions.py:PLATFORMS`):
  a platform module exposes `EDITOR_URL`, an alive-marker selector, and
  `build_document(page, doc, images_dir, log=print)`. It is registered in
  `sessions.PLATFORMS` and driven by `cli.py layout`.
- **Recon facts** (canonical block tree from
  `wp.data.select('core/block-editor').getBlocks()`): paste yields `core/heading`
  (with `level`), `core/list` (+`core/list-item`), `core/quote`, bold/italic inline,
  and `core/image` whose `url` flips from `data:` to `http(s)` once WP sideloads it.
  Captions ride in as separate `[[CAP:…]]` paragraphs after each image.
- **Liveness marker**: `.editor-document-tools__inserter-toggle` — a top-window
  element present only when the editor loads (i.e. logged in). `orchestrator.check_alive`
  does `page.wait_for_selector(marker)`, so the marker must be a top-frame CSS selector.
- **Test command** (Windows PowerShell or Bash): `python -m pytest -q`.
- **Reuse**: `src/habr_adapter.py` already has `_data_uri(path)` and a data-URI
  emit pattern (`emit_body(..., image_src=lambda f: _data_uri(images_dir / f))`).
  We mirror it (separate copy in `wp_adapter` — each adapter is self-contained, like
  the others; do NOT refactor habr's into a shared module in this plan, YAGNI).

---

## Task 1: Module skeleton — constants, `_data_uri`, `body_html`

**Files:**
- Create: `src/wp_adapter.py`
- Test: `tests/test_wp_adapter.py`

**Step 1: Write the failing test**

Create `tests/test_wp_adapter.py`:

```python
# tests/test_wp_adapter.py
from pathlib import Path

from src import wp_adapter
from src.ir import Document, Heading, Paragraph, Quote, Image, ListBlock, ListItem, Run


def test_body_html_emits_native_blocks_data_uri_images_and_caption_markers():
    images_dir = Path("in/synthetic/images")  # real PNGs exist here
    doc = Document(title="T", blocks=[
        Heading(level=2, runs=[Run("Head")]),
        Paragraph(runs=[Run("plain "), Run("bold", bold=True)]),
        ListBlock(ordered=False, items=[ListItem(runs=[Run("one")])]),
        Quote(runs=[Run("quoted")]),
        Image(file="image1.png", caption=[Run("cap one")]),
    ])
    html = wp_adapter.body_html(doc, images_dir)

    # Native Gutenberg-friendly structure (paste maps these to core blocks).
    assert "<h2>Head</h2>" in html
    assert "<strong>bold</strong>" in html
    assert "<ul><li>one</li></ul>" in html
    assert "<blockquote>quoted</blockquote>" in html  # NOT a <p> (unlike VC)
    # Images go in as data-URIs (WP sideloads them on paste).
    assert 'src="data:image/png;base64,' in html
    # Captions ride as [[CAP:]] markers for the post-paste cleanup pass.
    assert "[[CAP:cap one]]" in html


def test_constants_point_at_ruminlab():
    assert wp_adapter.EDITOR_URL == "https://ruminlab.ru/wp-admin/post-new.php"
    assert wp_adapter.ALIVE_SEL == ".editor-document-tools__inserter-toggle"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_wp_adapter.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.wp_adapter'`.

**Step 3: Write minimal implementation**

Create `src/wp_adapter.py`:

```python
"""Drive the WordPress / Gutenberg editor (ruminlab.ru) to build a draft.

One real Ctrl+V of our clean body HTML produces native Gutenberg blocks
(headings, lists, quote, bold/italic) and auto-sideloads <img> data-URIs into
the media library. The canvas is in an iframe, but the wp.data store lives on
the TOP window, so the title, image captions, and "save draft" are driven via
wp.data — the iframe is touched only for the single body paste. Visible browser,
shared client profile, STOPS at a saved draft (never publishes).
"""
import base64
import mimetypes
import time
from pathlib import Path

from src.emit_html import emit_body

SITE = "https://ruminlab.ru"
EDITOR_URL = f"{SITE}/wp-admin/post-new.php"
ALIVE_SEL = ".editor-document-tools__inserter-toggle"
CANVAS_SEL = 'iframe[name="editor-canvas"]'


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def body_html(doc, images_dir: Path) -> str:
    """Clean Gutenberg-paste HTML: real <blockquote>, <img> as data-URIs (WP
    sideloads them to the media library on paste), and captions as [[CAP:text]]
    marker paragraphs that the post-paste cleanup pass moves into each image's
    native caption."""
    return emit_body(
        doc, quote_as_paragraph=False, caption_marker=True, img_sep=" ",
        image_src=lambda f: _data_uri(images_dir / f),
    )
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_wp_adapter.py -q`
Expected: PASS (2 passed).

> If `<ul><li>one</li></ul>` assertion fails, check `emit_html.emit_body`'s list
> rendering — it emits `<ul>` with no whitespace between tags; the assertion matches
> that exact form. Do NOT change `emit_html`; fix the test to match its real output.

**Step 5: Commit**

```bash
git add src/wp_adapter.py tests/test_wp_adapter.py
git commit -m "feat(wp): wp_adapter skeleton — constants, _data_uri, body_html"
```

---

## Task 2: Register `ruminlab` in the platform registry

**Files:**
- Modify: `src/sessions.py` (import block near line 16; `PLATFORMS` dict near line 104)
- Modify: `tests/test_sessions_registry.py`

**Step 1: Update the failing tests**

In `tests/test_sessions_registry.py`, update the two whole-registry assertions and
add a contract test:

```python
def test_registry_has_all_platforms():
    assert set(sessions.PLATFORMS) == {
        "vc", "pikabu", "habr", "smartlab", "dzen", "lj", "dtf", "ruminlab"}


def test_known_platforms_helper():
    assert sessions.known_platforms() == [
        "dtf", "dzen", "habr", "lj", "pikabu", "ruminlab", "smartlab", "vc"]
```

Append a contract test:

```python
def test_ruminlab_registered_with_contract():
    entry = sessions.PLATFORMS["ruminlab"]
    assert callable(entry["build_document"])
    assert entry["editor_url"].startswith("http")
    assert entry["alive_marker"]
    # Plain WordPress login/password — standard CDP login (like VC/LJ), no manual_login.
    assert "manual_login" not in entry
    assert "ruminlab" in sessions.known_platforms()
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sessions_registry.py -q`
Expected: FAIL — `KeyError: 'ruminlab'` / set & list mismatches.

**Step 3: Implement the registration**

In `src/sessions.py`, add `wp_adapter` to the adapter import (line ~16):

```python
from src import vc_adapter, pikabu_adapter, habr_adapter, smartlab_adapter, dzen_adapter, lj_adapter, dtf_adapter, wp_adapter
```

Add an entry to `PLATFORMS` (after the `lj` entry, before the closing `}`):

```python
    "ruminlab": {
        "build_document": wp_adapter.build_document,
        # Liveness navigates here and waits for ALIVE_SEL (the editor inserter toggle,
        # a top-window element present only when the Gutenberg editor loads = logged in).
        "editor_url": wp_adapter.EDITOR_URL,
        "alive_marker": wp_adapter.ALIVE_SEL,
        # Plain WordPress login/password — standard open_context (like VC/LJ), no captcha.
    },
```

> `wp_adapter.build_document` does not exist yet (Task 3). The import of the symbol
> is fine (it's a module attribute resolved at call time, not import time) — but the
> registry tests only check `callable(entry["build_document"])`, which needs the
> attribute to EXIST. So Task 2 and Task 3 can be committed together, OR add a stub
> `def build_document(page, doc, images_dir, log=print): raise NotImplementedError`
> to `wp_adapter.py` now and flesh it out in Task 3. **Do the stub** — it keeps each
> task green.

Add the stub to `src/wp_adapter.py` (end of file):

```python
def build_document(page, doc, images_dir: Path, log=print):
    raise NotImplementedError  # implemented in Task 3
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sessions_registry.py tests/test_wp_adapter.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/sessions.py src/wp_adapter.py tests/test_sessions_registry.py
git commit -m "feat(wp): register ruminlab platform in the session registry"
```

---

## Task 3: Implement `build_document` (browser flow)

**Files:**
- Modify: `src/wp_adapter.py` (replace the Task-2 stub)

No unit test — this is browser automation, covered by the Task 4 e2e run. Write the
complete flow, then verify in Task 4.

**Step 1: Add the JS snippets and helpers**

In `src/wp_adapter.py`, after `body_html`, add:

```python
def _set_clipboard(page, html):
    """Put clean body HTML on the real clipboard (text/html + text/plain).

    A real Ctrl+V of THIS clean html is what Gutenberg parses into one core block
    per element. Requires clipboard-write permission (granted in build_document).
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


# Editor is ready when the block-editor store is up (logged in AND editor loaded).
# wp.data lives on the TOP window regardless of the iframed canvas.
_EDITOR_READY = ("() => !!(window.wp && wp.data && wp.data.select('core/block-editor')"
                 " && wp.data.select('core/block-editor').getBlocks)")

_SET_TITLE = "(t) => wp.data.dispatch('core/editor').editPost({title: t})"

# Ensure a first empty paragraph block exists and return its clientId, so we can
# focus the BODY (not the title) for the paste. Pasting into the title swallows the
# first body block (observed in recon).
_FIRST_BODY_CLIENT_ID = r"""
() => {
  const sel = wp.data.select('core/block-editor');
  const dispatch = wp.data.dispatch('core/block-editor');
  const blocks = sel.getBlocks();
  if (blocks.length) return blocks[0].clientId;
  const b = wp.blocks.createBlock('core/paragraph');
  dispatch.insertBlocks(b);
  return b.clientId;
}
"""

# All core/image blocks have a real http(s) url (WP finished sideloading them).
_IMAGES_SETTLED = r"""
() => {
  const imgs = wp.data.select('core/block-editor').getBlocks()
      .filter(b => b.name === 'core/image');
  return imgs.length === 0 || imgs.every(b => /^https?:/.test(b.attributes.url || ''));
}
"""

# Move each [[CAP:text]] paragraph that immediately follows a core/image into that
# image's native caption, then remove the marker paragraph. Returns the count set.
_APPLY_CAPTIONS = r"""
() => {
  const sel = wp.data.select('core/block-editor');
  const dispatch = wp.data.dispatch('core/block-editor');
  const blocks = sel.getBlocks();
  const text = a => (typeof a.content === 'string') ? a.content
                  : (a.content && a.content.text) ? a.content.text : '';
  let n = 0;
  for (let i = 0; i < blocks.length - 1; i++) {
    if (blocks[i].name !== 'core/image') continue;
    const next = blocks[i + 1];
    if (next.name !== 'core/paragraph') continue;
    const m = text(next.attributes).match(/^\s*\[\[CAP:([\s\S]*)\]\]\s*$/);
    if (!m) continue;
    dispatch.updateBlockAttributes(blocks[i].clientId, {caption: m[1]});
    dispatch.removeBlock(next.clientId);
    n++;
  }
  return n;
}
"""

_SAVE_DRAFT = "() => wp.data.dispatch('core/editor').savePost()"

# Saved as a draft: not currently saving AND status is 'draft'.
_DRAFT_SAVED = r"""
() => {
  const s = wp.data.select('core/editor');
  return !s.isSavingPost() && s.getCurrentPost().status === 'draft';
}
"""
```

**Step 2: Replace the stub `build_document` with the full flow**

```python
def build_document(page, doc, images_dir: Path, log=print):
    log(f"Opening editor: {EDITOR_URL}")
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.goto(EDITOR_URL, wait_until="domcontentloaded")
    page.wait_for_function(_EDITOR_READY, timeout=30000)
    time.sleep(1)

    # 1. Title via wp.data (pasting into the title field would swallow the first block).
    log(f"Title: {doc.title!r}")
    page.evaluate(_SET_TITLE, doc.title)

    # 2. Body in ONE real Ctrl+V into the first body block (inside the canvas iframe).
    html = body_html(doc, images_dir)
    _set_clipboard(page, html)
    client_id = page.evaluate(_FIRST_BODY_CLIENT_ID)
    page.frame_locator(CANVAS_SEL).locator(
        f'[data-block="{client_id}"] [contenteditable="true"]').first.click()
    log("Pasting body via real clipboard…")
    page.keyboard.press("Control+V")
    time.sleep(1)
    n_blocks = page.evaluate(
        "() => wp.data.select('core/block-editor').getBlocks().length")
    log(f"Pasted; {n_blocks} top-level block(s).")

    # 3. Wait for WP to sideload pasted data-URI images into the media library.
    from src.ir import Image  # local import keeps the module's import block tidy
    n_images = sum(1 for b in doc.blocks if isinstance(b, Image))
    if n_images:
        log(f"Waiting for {n_images} image(s) to sideload to the media library…")
        try:
            page.wait_for_function(_IMAGES_SETTLED, timeout=120000)
        except Exception as e:  # noqa: BLE001 — best-effort, report and continue
            log(f"  image sideload wait timed out ({str(e)[:80]})")

    # 4. Move [[CAP:]] marker paragraphs into native image captions.
    try:
        n_caps = page.evaluate(_APPLY_CAPTIONS)
        log(f"Captions applied: {n_caps}")
    except Exception as e:  # noqa: BLE001
        log(f"  caption pass failed ({str(e)[:80]})")

    # 5. Save as a draft. NEVER publishes.
    log("Saving draft…")
    page.evaluate(_SAVE_DRAFT)
    try:
        page.wait_for_function(_DRAFT_SAVED, timeout=30000)
        log(f"Draft saved (status=draft): {page.url}")
    except Exception:  # noqa: BLE001
        log(f"WARNING: did not confirm draft saved; current: {page.url}")
```

Remove the `from src.ir import Image` line if you prefer it at the top of the module
(either is fine; keep ONE).

**Step 3: Sanity-check it imports and the registry is still green**

Run: `python -m pytest tests/test_wp_adapter.py tests/test_sessions_registry.py -q`
Expected: PASS (the registry now sees a real `build_document`).

Also run the full suite to ensure nothing regressed:
Run: `python -m pytest -q`
Expected: PASS (all existing tests still green).

**Step 4: Commit**

```bash
git add src/wp_adapter.py
git commit -m "feat(wp): build_document — paste body + wp.data captions/title/save-draft"
```

---

## Task 4: End-to-end validation on `in/synthetic`

**Files:** none (validation run; may produce a tiny selector fix to `src/wp_adapter.py`).

> Per the project's "test on synthetic" rule, validate on `in/synthetic` (~10
> blocks), not a long real article. The login is interactive and the browser must be
> visible, so the USER runs these via the `!` prefix.

**Step 1: Ensure a logged-in profile for the test client**

The e2e uses a client profile (e.g. `default`). If `ruminlab` is not logged in there,
log in once (opens one Chrome with a tab per platform — log into ruminlab.ru/wp-admin):

Run (user, via `!`): `! python cli.py login default`

Then confirm liveness:

Run (user, via `!`): `! python cli.py status default`
Expected: a `ruminlab  alive` row.

**Step 2: Run the layout for ruminlab only**

Run (user, via `!`): `! python cli.py layout synthetic default ruminlab`

Expected console (from `build_document`): `Title: …`, `Pasted; N top-level block(s).`,
`Waiting for 2 image(s)…`, `Captions applied: 2`, `Draft saved (status=draft): …`.

**Step 3: Verify in the open browser window (human check)**

Confirm in the editor that stays open:
- Title is the doc title (NOT the first paragraph — that was the recon bug; the
  `_FIRST_BODY_CLIENT_ID` focus fix prevents it).
- H2/H3 headings, both lists, the quote (native quote block), bold + italic present.
- Both images are real media-library images (not broken/data-URI), each with its
  caption under it, and NO leftover `[[CAP:…]]` or `[[IMG …]]` text.
- Post status reads "Черновик" (draft); nothing was published.

**Step 4: If the title still swallows the first block, or the paste lands wrong**

The one fragile spot is focusing the body. If verification shows the first block in
the title or the body empty, adjust the focus step in `build_document` (Task 3,
step 2):
- Try clicking the block's editable via its `data-block` then pressing `End` before
  `Ctrl+V`, or
- Click `.block-editor-default-block-appender__content` inside the canvas frame instead.
Re-run Step 2 until verification passes, then commit the fix:

```bash
git add src/wp_adapter.py
git commit -m "fix(wp): focus body block reliably before paste"
```

**Step 5: (Optional) Probe B — native captions via `<figure><figcaption>`**

Quick experiment to possibly drop the caption cleanup pass. Temporarily change
`body_html` to emit a `<figure>` with `<figcaption>` per image (instead of the
`[[CAP:]]` marker) and re-run Step 2. Inspect
`wp.data.select('core/block-editor').getBlocks()` (or the editor): if each
`core/image` came in with its `caption` already set, simplify the adapter (emit
figcaption, delete `_APPLY_CAPTIONS` and step 4). If captions are dropped on paste,
REVERT to the `[[CAP:]]` + cleanup approach (Tasks 1/3 as written). Commit only if
it's a net simplification that still passes Step 3 verification.

---

## Task 5: Documentation

**Files:**
- Modify: `docs/platform-notes.md` (title line ~9; add a WordPress section before the
  "Onboarding a new platform" section near line 443)
- Modify: `docs/plans/2026-06-02-wp-adapter-design.md` (status line)

**Step 1: Add the WordPress section to `docs/platform-notes.md`**

Update the H1 to include WordPress:

```markdown
# Platform notes (VC + Pikabu + Habr + Smartlab + Dzen + LiveJournal + WordPress)
```

Insert before `## Onboarding a new platform`:

```markdown
## WordPress / Gutenberg — block editor at `/wp-admin/post-new.php` (ruminlab.ru)

Our own site. The Gutenberg editor's body is a block model rendered inside an
**iframe** (`iframe[name="editor-canvas"]`), but the **`wp.data` store lives on the
TOP window** — so we set the title, fix captions, and save the draft via `wp.data`
and touch the iframe only for the single body paste. Adapter: `src/wp_adapter.py`.

### Navigation & auth
- New-post editor: `https://ruminlab.ru/wp-admin/post-new.php`.
- Auth is an **ordinary login/password** — STANDARD `open_context` (like VC/LJ), NO
  `manual_login` (no captcha under CDP). `python cli.py login <client>` (log into the
  ruminlab.ru/wp-admin tab).
- Liveness marker: `.editor-document-tools__inserter-toggle` (top-window inserter
  toggle, present only when the editor loads = logged in).

### Body — ONE real clipboard paste (clean HTML)
`emit_body(doc, quote_as_paragraph=False, caption_marker=True, img_sep=" ",
image_src=<data-URI>)` then a real `Ctrl+V` into the FIRST body block. Gutenberg's
paste maps cleanly to native core blocks — verified via
`wp.data.select('core/block-editor').getBlocks()`:
`<h2>/<h3>` → `core/heading` (correct `level`); `<ul>/<ol>` → `core/list`
(+`core/list-item`); `<blockquote>` → `core/quote` (NO convert pass, unlike VC/Habr);
`<strong>/<em>` survive inline.
> **Set the title via `wp.data`, paste into the BODY.** Pasting while the caret is in
> the title field swallows the first body block into the title (observed in recon).
> Set `wp.data.dispatch('core/editor').editPost({title})`, then focus the first body
> block by its `clientId` (`[data-block="<id>"] [contenteditable]` inside the canvas
> frame) before `Ctrl+V`.

### Images — data-URI paste, WP auto-sideloads (no file chooser, no markers)
Emit each local image as `<img src="data:…base64…">`. On paste WP **sideloads** it
into the **media library**: the resulting `core/image` gets a real attachment `id`
and its `url` flips from `data:` to `https://ruminlab.ru/wp-content/uploads/…`.
**Wait for every `core/image` `url` to be `http(s)`** before continuing (async).

### Captions — `[[CAP:]]` marker → native caption (wp.data cleanup pass)
Paste does NOT attach captions: each `[[CAP:text]]` marker lands as its own paragraph
after the image. After the images settle, run one `wp.data` pass: for each
`core/image` immediately followed by a `[[CAP:…]]` paragraph,
`updateBlockAttributes(image,{caption})` + `removeBlock(markerParagraph)`.

### Stop point — saved draft, never publish
`wp.data.dispatch('core/editor').savePost()`, then wait for `!isSavingPost()` and
`getCurrentPost().status === 'draft'`. "Опубликовать" is never clicked.
```

**Step 2: Mark the design implemented**

In `docs/plans/2026-06-02-wp-adapter-design.md`, change the status line to:
`**Status:** implemented; e2e-validated on in/synthetic`.

**Step 3: Commit**

```bash
git add docs/platform-notes.md docs/plans/2026-06-02-wp-adapter-design.md
git commit -m "docs(wp): platform notes for WordPress/Gutenberg; mark design implemented"
```

---

## Task 6: Cleanup

**Files:**
- Delete: `recon_wp.py`, `recon/` (untracked recon artifacts)
- Modify: `.gitignore` (add `recon/`)

**Step 1: Remove the throwaway recon script and its output**

```bash
git rm -f --ignore-unmatch recon_wp.py
```

(`recon_wp.py` is untracked if never committed — then just delete the file. `recon/`
output and the `.profiles/_recon` profile are not tracked; `.profiles/` is already
gitignored.)

Delete the `recon/` directory (PowerShell): `Remove-Item -Recurse -Force recon`.

**Step 2: Ignore future recon output**

Add to `.gitignore` (next to the existing `discovery/` line):

```
recon/
```

**Step 3: Confirm the suite is green and the tree is clean**

Run: `python -m pytest -q`
Expected: PASS.
Run: `git status`
Expected: only intended changes; no `recon_wp.py`/`recon/` left.

**Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore(wp): drop throwaway recon script; ignore recon/ output"
```

---

## Done criteria

- `python -m pytest -q` green (new `test_wp_adapter.py` + updated registry tests).
- `python cli.py layout synthetic <client> ruminlab` builds a WordPress draft with
  correct blocks, media-library images, and captions, status `draft`, nothing
  published (Task 4 human verification passed).
- `docs/platform-notes.md` documents the WordPress adapter; design doc marked
  implemented.
- After merge: update `MEMORY.md` with a `project_wp_adapter.md` pointer (one line),
  mirroring the other adapter memories.

## Finishing

When all tasks pass, use superpowers:finishing-a-development-branch to decide
merge/PR/cleanup for `feat/wp-adapter`.

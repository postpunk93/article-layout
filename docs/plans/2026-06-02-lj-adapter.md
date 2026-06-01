# LiveJournal Adapter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an `lj` platform that lays out a parsed GDoc article as an autosaved
draft in LiveJournal's new post editor (`https://www.livejournal.com/post/`), never
publishing.

**Architecture:** New `src/lj_adapter.py` mirrors `src/dzen_adapter.py` — the LJ body
editor is Draft.js (recon-verified), so a single clean-HTML clipboard paste builds the
whole body, then `[[IMG:file]]` markers are replaced by natively uploaded images, and
the run stops at the autosaved draft. Registered in `src/sessions.py` `PLATFORMS` with
standard `open_context` login (no `manual_login` unless a login captcha appears).

**Tech Stack:** Python, Playwright (sync API, `channel="chrome"`), pytest. Reuse
`src/emit_html.emit_body` and the Draft.js patterns proven in `src/dzen_adapter.py`.

**Design doc:** `docs/plans/2026-06-02-lj-adapter-design.md` (read it first — it records
the live recon: selectors, the surviving-paste probe, and the three open probes (a)(b)(c)).

**Working scratch (already on disk, used for live probes; DELETE in Task 8):**
`recon_lj.py`, `probe_lj_paste.py`, `recon_lj_dump.json`, `recon_summary.txt`.
The `default` profile is logged into LJ — use it for every live verification below.

---

## Task 1: `body_html` pure helper

**Files:**
- Create: `src/lj_adapter.py`
- Test: `tests/test_lj_adapter.py`

**Step 1: Write the failing test** (mirror `tests/test_dzen_adapter.py`)

```python
# tests/test_lj_adapter.py
from src import lj_adapter
from src.ir import Document, Paragraph, Quote, Image, Run


def test_body_html_emits_real_blockquote_and_img_markers():
    doc = Document(title="T", blocks=[
        Paragraph(runs=[Run("hello")]),
        Quote(runs=[Run("quoted")]),
        Image(file="image1.png", caption=[Run("cap")]),
    ])
    html = lj_adapter.body_html(doc)
    assert "<blockquote>quoted</blockquote>" in html
    assert "[[IMG:image1.png]]" in html
    assert "data:image" not in html
```

> NOTE: the `[[CAP:` assertion is intentionally omitted here — whether captions ride as
> a marker depends on probe (b) in Task 5. Add the correct caption assertion in Task 5
> once the native-caption question is settled.

**Step 2: Run test to verify it fails**

Run: `py -m pytest tests/test_lj_adapter.py -v`
Expected: FAIL (`module 'src.lj_adapter' has no attribute 'body_html'` / import error).

**Step 3: Write minimal implementation**

```python
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
# Logged-in marker: the Draft.js body mounts only for an authenticated user.
ALIVE_SEL = BODY_SEL


def body_html(doc):
    """Clean body HTML for the paste: real <blockquote> (LJ makes a native quote
    block), images as [[IMG:file]] markers replaced after the paste."""
    return emit_body(doc, caption_marker=False, quote_as_paragraph=False, img_sep=":")
```

> `caption_marker` may flip to `True` in Task 5 depending on probe (b). Leave it
> `False` for now to match the Task 1 test.

**Step 4: Run test to verify it passes**

Run: `py -m pytest tests/test_lj_adapter.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/lj_adapter.py tests/test_lj_adapter.py
git commit -m "feat(lj): body_html helper (Draft.js clean-HTML paste)"
```

---

## Task 2: Open editor + dismiss restore-draft modal

**Files:**
- Modify: `src/lj_adapter.py`

No unit test — this is browser automation, verified by a live probe. Build it directly
and confirm against the live editor.

**Step 1: Add `_open_editor`**

```python
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
```

**Step 2: Live-verify**

Write a throwaway snippet (or extend `recon_lj.py`) that runs `open_context(p, "default")`
then `_open_editor(page, print)`. Confirm: lands on the editor, modal dismissed, no
exception. Expected log: "Editor ready: https://www.livejournal.com/post/".

**Step 3: Commit**

```bash
git add src/lj_adapter.py
git commit -m "feat(lj): open editor and dismiss restore-draft modal"
```

---

## Task 3: Set title + paste body

**Files:**
- Modify: `src/lj_adapter.py`

**Step 1: Add clipboard + title/body helpers** (reuse the Dzen pattern verbatim where
it applies; LJ's title is a `textarea`, so `fill` it instead of typing into contenteditable)

```python
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
```

**Step 2: Live-verify**

Extend the throwaway snippet: after `_open_editor`, call `_set_title_and_body` with a
parsed sample (`parse(Path("in/lists-quotes/index.html").read_text(encoding="utf-8"))`).
Grant clipboard perms first (`page.context.grant_permissions(["clipboard-read","clipboard-write"])`).
Expected: title textarea filled; body shows the article text (the probe already proved
the 72-block paste survives). Eyeball the browser.

**Step 3: Commit**

```bash
git add src/lj_adapter.py
git commit -m "feat(lj): set title and paste body"
```

---

## Task 4: Resolve probe (a) — quote rendering

**Files:**
- Modify: `src/lj_adapter.py` (only if a convert pass is needed)

**Step 1: Probe** — after a body paste with a `<blockquote>`, inspect whether LJ
rendered a native quote block. In the live page evaluate the block classes around the
quoted text (look for an LJ quote/`blockquote` block class vs a plain paragraph).
`in/lists-quotes` contains quotes — use it.

**Step 2: Decide**
- If `<blockquote>` → native quote block: nothing to do, note it in a code comment.
- If it stays a plain paragraph: add a post-paste convert pass (locate quote blocks by
  the marker the parser preserves, select the line, apply the «Цитата» slash command),
  mirroring how VC restores quotes. Keep it minimal (YAGNI).

**Step 3: Commit** (only if code changed)

```bash
git add src/lj_adapter.py
git commit -m "feat(lj): ensure pasted quotes become native quote blocks"
```

---

## Task 5: Image upload + caption (resolve probe (b))

**Files:**
- Modify: `src/lj_adapter.py`
- Modify: `tests/test_lj_adapter.py` (caption assertion, once settled)

**Step 1: Probe the image-insert gesture + caption field.** Against the live editor with
the body already pasted, determine how an upload lands at a marker block. Two candidate
mechanisms, prefer the simplest that works:
- (A) Focus the marker block, clear its text (`Home`,`Shift+End`,`Delete` — NOT
  `Ctrl+A`, which selects the whole Draft.js editor), open the insert panel
  (`js--add-panel-trigger` "+" or type `/` → «Загрузить изображение»), then
  `set_input_files` on the revealed hidden `input[type=file][accept*=".webp"]`.
- (B) If a stable hidden file input is always present, `set_input_files` directly and
  move the resulting image to the marker position.

Also check: does the inserted image block expose a **native caption field**?

**Step 2: Implement `_replace_marker_with_image`** following the Dzen version
(`src/dzen_adapter.py:91`) adapted to the gesture found in Step 1. Wait for the uploaded
image to get a real CDN `src` before continuing. Set the caption per Step 1's finding:
- native caption field → set it natively; keep `body_html` `caption_marker=False`.
- no native field → set `caption_marker=True` in `body_html`, render caption as a
  following paragraph, and (optionally) leave it as plain text under the image.

**Step 3: Add `_strip_blank_after_images`** only if the upload leaves a stray blank
paragraph (as Dzen does, `src/dzen_adapter.py:147`). Skip if not needed (YAGNI).

**Step 4: Update the caption unit test** in `tests/test_lj_adapter.py` to assert the
chosen behavior (`[[CAP:` present iff `caption_marker=True`). Run:
`py -m pytest tests/test_lj_adapter.py -v` → PASS.

**Step 5: Live-verify** end-to-end image insertion on `in/lists-quotes` (10 images):
all markers replaced by uploaded images with correct captions, no `[[IMG:` left.

**Step 6: Commit**

```bash
git add src/lj_adapter.py tests/test_lj_adapter.py
git commit -m "feat(lj): native image upload and captions"
```

---

## Task 6: Stop at autosaved draft (resolve probe (c))

**Files:**
- Modify: `src/lj_adapter.py`

**Step 1: Probe the autosave indicator** — find the selector/text that signals the
draft is saved (Dzen waits for `/сохранен[оы]/i`). Inspect the editor header/status
area after edits dirty the page.

**Step 2: Implement `build_document`** wiring it all together, ending by waiting for the
saved indicator and NEVER clicking `PUBLISH_SEL`:

```python
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
    # _strip_blank_after_images(page, log)  # only if Task 5 showed stray blanks
    # Stop at the autosaved draft — NEVER click PUBLISH_SEL.
    try:
        page.wait_for_function(
            "(sel) => { const s = document.querySelector(sel); return s && /<SAVED-REGEX>/i.test(s.innerText||''); }",
            arg="<STATUS_SEL>",
            timeout=20000,
        )
        log("Draft autosaved.")
    except Exception:  # noqa: BLE001
        log(f"WARNING: did not observe autosave; draft may still be saving. URL: {page.url}")
```

Replace `<STATUS_SEL>`/`<SAVED-REGEX>` with the values found in Step 1.

**Step 3: Live-verify** the full `build_document` against `in/lists-quotes`: title, body,
images, and a logged "Draft autosaved." Confirm in the browser that a draft exists and
nothing was published.

**Step 4: Commit**

```bash
git add src/lj_adapter.py
git commit -m "feat(lj): stop at autosaved draft (never publish)"
```

---

## Task 7: Register `lj` in the platform registry

**Files:**
- Modify: `src/sessions.py:16` (import) and `src/sessions.py` `PLATFORMS`
- Modify: `tests/test_sessions_registry.py`

**Step 1: Update the failing registry tests** (TDD — change expectations first)

```python
# test_registry_has_all_platforms
assert set(sessions.PLATFORMS) == {"vc", "pikabu", "habr", "smartlab", "dzen", "lj"}
# test_known_platforms_helper
assert sessions.known_platforms() == ["dzen", "habr", "lj", "pikabu", "smartlab", "vc"]
```

Add a contract test:

```python
def test_lj_registered_with_contract():
    entry = sessions.PLATFORMS["lj"]
    assert callable(entry["build_document"])
    assert entry["editor_url"].startswith("http")
    assert entry["alive_marker"]
    # Standard CDP login (like VC/Smartlab) — no manual_login unless a captcha appears.
    assert "manual_login" not in entry
    assert "lj" in sessions.known_platforms()
```

**Step 2: Run to verify failure**

Run: `py -m pytest tests/test_sessions_registry.py -v`
Expected: FAIL (`KeyError: 'lj'` / set mismatch).

**Step 3: Register the platform** in `src/sessions.py`

```python
from src import vc_adapter, pikabu_adapter, habr_adapter, smartlab_adapter, dzen_adapter, lj_adapter
...
    "lj": {
        "build_document": lj_adapter.build_document,
        "editor_url": lj_adapter.POST_URL,
        "alive_marker": lj_adapter.ALIVE_SEL,  # BODY_SEL, mounts only when logged in
    },
```

**Step 4: Run the full suite**

Run: `py -m pytest -q`
Expected: all PASS.

**Step 5: Commit**

```bash
git add src/sessions.py tests/test_sessions_registry.py
git commit -m "feat(lj): register lj platform in session registry"
```

---

## Task 8: End-to-end, cleanup, docs

**Files:**
- Delete: `recon_lj.py`, `probe_lj_paste.py`, `recon_lj_dump.json`, `recon_summary.txt`
- Modify: docs/CLAUDE wording if it enumerates platforms (grep first)

**Step 1: Full E2E via the CLI.** With the `default` profile logged in:

Run: `py cli.py status default` (lj should report alive), then
`py cli.py layout default lj <sample-slug>` (whatever the CLI's layout signature is —
confirm against `cli.py`). Verify: one window, LJ draft built with title/body/images,
stopped at autosave, nothing published.

**Step 2: Verify login under CDP is sufficient.** If LJ login ever needs a fresh,
profile-less browser and shows a captcha under CDP, add `manual_login: True` +
`login_url` to the registry entry and update the contract test. Otherwise leave as-is.

**Step 3: Delete scratch files**

```bash
git rm -f recon_lj.py probe_lj_paste.py recon_lj_dump.json recon_summary.txt
```
(They may be untracked — use `rm` for those.)

**Step 4: Docs sweep** — grep for platform enumerations (`grep -rn "smartlab" docs CLAUDE.md README* 2>/dev/null`)
and add `lj` where the set is listed. Keep it factual.

**Step 5: Run the full suite one last time**

Run: `py -m pytest -q`
Expected: all PASS.

**Step 6: Commit**

```bash
git add -A
git commit -m "feat(lj): e2e-validated LiveJournal adapter; remove scratch probes"
```

---

## Done criteria

- `py -m pytest -q` green.
- `cli.py layout` builds a complete LJ draft (title, structured body, uploaded images
  with captions) and stops at autosave without publishing.
- No scratch files; `lj` listed wherever platforms are enumerated.
- Memory updated (`project_lj_adapter.md` + MEMORY.md pointer) noting branch, approach,
  and that it's validated end-to-end — matching the other adapter memories.
```

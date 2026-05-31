# Smartlab Adapter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `smartlab` platform adapter that lays out a GDoc-sourced article into smart-lab.ru's post editor and stops at a draft/preview state, never publishing.

**Architecture:** Discovery-first (approach A). First land the deterministic plumbing (a skeleton `src/smartlab_adapter.py` + registration in `sessions.PLATFORMS` + a registry test) — this needs no knowledge of the editor. Then log in and inspect the live editor DOM, recording findings in `docs/platform-notes.md`. Only then finalize `build_document` against the discovered engine, reusing `emit_html.emit_body` and (where they fit) the Habr helpers. No new IR; `cli.py` and `orchestrator.py` are untouched — they are already generic over platforms.

**Tech Stack:** Python, Playwright (sync API, installed Chrome via `channel="chrome"`), pytest. Reuses `src/emit_html.py`, `src/sessions.py`, `src/ir.py`.

**Design:** `docs/plans/2026-05-31-smartlab-adapter-design.md`

**Branch:** `feat/smartlab-adapter` (already created from `main`, design already committed).

**Given facts:**
- `ADD_URL = "https://smart-lab.ru/topic/add/"`, `LOGIN_URL = "https://smart-lab.ru/login/"`, `HOME_URL = "https://smart-lab.ru/"`.
- Auth: ordinary login/password; start with the standard Playwright login flow (no `manual_login`). Escalate only if discovery finds a CDP-blanking captcha.
- Scope = same as other adapters (title + headings + bold/italic + lists + quotes + images with captions), stop before publish.

---

## Phase 1 — Deterministic plumbing (no editor knowledge needed)

### Task 1: Skeleton adapter module with constants and a placeholder `build_document`

**Files:**
- Create: `src/smartlab_adapter.py`

**Step 1: Write the module**

Mirror the shape of `src/habr_adapter.py` (module docstring + URL/selector constants + `build_document`). The selectors are placeholders confirmed at discovery (Phase 2); the body logic is intentionally a stub that raises until Phase 3 — Phase 1 only needs the constants and the callable to exist so the registry is wireable.

```python
"""Drive smart-lab.ru's post editor to build a draft.

Editor engine is determined by discovery (see docs/platform-notes.md
"Smartlab"); until then BODY_SEL/TITLE_SEL/ALIVE_SEL are best-guess
placeholders and build_document's body strategy is finalized in Phase 3.

Auth is an ordinary login/password (standard Playwright login flow). We build
the body from the shared IR via emit_html.emit_body, drive the editor to a
draft/preview, and STOP — never publish.
"""
from pathlib import Path

from src.emit_html import emit_body
from src.ir import Image, Quote

HOME_URL = "https://smart-lab.ru/"
LOGIN_URL = "https://smart-lab.ru/login/"
ADD_URL = "https://smart-lab.ru/topic/add/"

# Confirmed at discovery (Phase 2). ALIVE_SEL must be an element that renders
# ONLY for a logged-in user (is_alive navigates to ADD_URL and waits for it).
ALIVE_SEL = "#title"      # placeholder — title field of the post form
TITLE_SEL = "#title"      # placeholder
BODY_SEL = "#text"        # placeholder — editor body / textarea


def build_document(page, doc, images_dir, log=print):
    raise NotImplementedError(
        "smartlab build_document is finalized in Phase 3 after editor discovery"
    )
```

**Step 2: Verify it imports**

Run: `python -c "from src import smartlab_adapter as s; print(s.ADD_URL)"`
Expected: prints `https://smart-lab.ru/topic/add/`

**Step 3: Commit**

```bash
git add src/smartlab_adapter.py
git commit -m "feat(smartlab): skeleton adapter — constants + placeholder build_document"
```

---

### Task 2: Register `smartlab` in the platform registry (TDD)

**Files:**
- Test: `tests/test_sessions_registry.py`
- Modify: `src/sessions.py` (import + `PLATFORMS`)

**Step 1: Write the failing tests**

In `tests/test_sessions_registry.py`, update `test_registry_has_all_platforms` and `test_known_platforms_helper` and add a smartlab contract test:

```python
def test_registry_has_all_platforms():
    assert set(sessions.PLATFORMS) == {"vc", "pikabu", "habr", "smartlab"}


def test_known_platforms_helper():
    assert sessions.known_platforms() == ["habr", "pikabu", "smartlab", "vc"]


def test_smartlab_registered_with_contract():
    entry = sessions.PLATFORMS["smartlab"]
    assert callable(entry["build_document"])
    assert entry["editor_url"].startswith("http")
    assert entry["alive_marker"]
    assert "smartlab" in sessions.known_platforms()
```

(`test_each_platform_entry_is_complete` already loops over all entries — it will cover smartlab automatically.)

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sessions_registry.py -v`
Expected: FAIL — `KeyError: 'smartlab'` / set mismatch.

**Step 3: Register the platform**

In `src/sessions.py`, add `smartlab_adapter` to the existing adapter import line:

```python
from src import vc_adapter, pikabu_adapter, habr_adapter, smartlab_adapter
```

Add to the `PLATFORMS` dict (standard login → no `manual_login` key, like vc/pikabu):

```python
    "smartlab": {
        "build_document": smartlab_adapter.build_document,
        # is_alive navigates here and waits for ALIVE_SEL (a logged-in-only
        # element). Editor form only renders for an authenticated user.
        "editor_url": smartlab_adapter.ADD_URL,
        "alive_marker": smartlab_adapter.ALIVE_SEL,
    },
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sessions_registry.py -v`
Expected: PASS (all registry tests green).

**Step 5: Run the full suite (no regressions)**

Run: `python -m pytest -q`
Expected: PASS.

**Step 6: Commit**

```bash
git add tests/test_sessions_registry.py src/sessions.py
git commit -m "feat(smartlab): register adapter in platform registry"
```

---

## Phase 2 — Login + editor discovery (live browser, manual)

> This phase is interactive and observational — no committed code except the
> notes file and any selector constant fixes it produces. Run commands yourself
> with `! python ...` so output lands in the session.

### Task 3: Log in and confirm liveness

**Step 1: Log in**

Run: `! python cli.py login <client> smartlab`
- A Chrome window opens (standard Playwright flow). Log in with the smart-lab.ru account, then press Enter in the terminal.
- Expected: "Saved session for <client>/smartlab."

**Step 2: Check status**

Run: `! python cli.py status <client>`
- Expected: row `smartlab  alive`.
- **If `DEAD`:** the placeholder `ALIVE_SEL` (`#title`) is wrong for the logged-in editor. Open `ADD_URL` in the logged-in window, find a logged-in-only element, and fix `ALIVE_SEL` in `src/smartlab_adapter.py`. Re-run status until `alive`.
- **If login shows a captcha that renders blank:** STOP the standard flow — escalate to `manual_login` (see Task 4b).

### Task 4: Inspect the editor DOM and record findings

**Step 1: Open the editor and inspect**

With the logged-in profile, open the post form and inspect the DOM. A quick scripted probe (run yourself) that dumps the editor shape:

```bash
! python -c "from playwright.sync_api import sync_playwright; from src import sessions; \
import json; \
p=sync_playwright().start(); ctx,page=sessions.open_context(p,'<client>','smartlab',headless=False); \
page.goto(sessions.smartlab_adapter.ADD_URL, wait_until='domcontentloaded'); \
input('Inspect in DevTools, then Enter...'); ctx.close(); p.stop()"
```

Use DevTools (Elements) to answer the discovery checklist.

**Step 2: Answer the discovery checklist** (from the design):

1. **Editor type** — Tiptap/ProseMirror? CKEditor/TinyMCE (iframe)? raw `<textarea>`? BBCode/Markdown source? (look at DOM classes, `contenteditable`, iframe).
2. **Title** — separate field or first node of the body. Confirm `TITLE_SEL`.
3. **Paste behavior** — does a synthetic HTML paste keep bold/italic/lists/headings, or land flat?
4. **Images** — auto-upload from a pasted data-URI (like Habr)? a button / `<input type=file>`? separate upload endpoint? native caption field?
5. **Quotes / captions** — native quote + image-caption fields, or emulate with markers?
6. **Stop button** — "Предпросмотр" / "Сохранить черновик" / "Далее" — where it is safe to stop without publishing.
7. **Login captcha** — present or not.

**Step 3: Record findings in `docs/platform-notes.md`**

Add a new "Smartlab" section (mirror the existing "Habr" section's style): editor engine, confirmed selectors, paste fidelity, image transport, quote/caption handling, stop button text/selector, captcha verdict, and which body strategy (1 HTML-paste / 2 clipboard / 3 markup) Phase 3 will use.

**Step 4: Fix the placeholder constants**

Update `ALIVE_SEL`, `TITLE_SEL`, `BODY_SEL` in `src/smartlab_adapter.py` to the confirmed selectors. Re-run `! python cli.py status <client>` → `alive`. Re-run `python -m pytest tests/test_sessions_registry.py -q` → PASS.

**Step 5: Commit the discovery**

```bash
git add docs/platform-notes.md src/smartlab_adapter.py
git commit -m "docs(smartlab): record editor discovery + confirm selectors"
```

### Task 4b (CONDITIONAL): Escalate to manual_login if captcha blanks under CDP

Only if Step 1/Task 3 found a CDP-blanking captcha. In `src/sessions.py` `PLATFORMS["smartlab"]`, add `"manual_login": True` and `"login_url": smartlab_adapter.LOGIN_URL` (exactly like the `habr` entry). Re-run login (`cmd_login` will use the system-Chrome path automatically). Commit: `feat(smartlab): manual_login (login captcha blanks under CDP)`.

---

## Phase 3 — Implement `build_document` against the discovered engine

> Pick ONE body strategy based on the Phase 2 verdict. Each strategy reuses
> `emit_html.emit_body`. The Habr adapter (`src/habr_adapter.py`) is the
> reference for helpers — copy only what fits. Replace the `NotImplementedError`
> stub from Task 1.

### Task 5: Implement the chosen body strategy

**Files:**
- Modify: `src/smartlab_adapter.py`

**Common structure** (all strategies):

```python
def build_document(page, doc, images_dir, log=print):
    images_dir = Path(images_dir)
    log(f"Opening editor ({ADD_URL})")
    page.goto(ADD_URL, wait_until="domcontentloaded")
    page.wait_for_selector(BODY_SEL, timeout=30000)

    log(f"Title: {doc.title!r}")
    page.click(TITLE_SEL)
    page.keyboard.type(doc.title)

    # --- body: per chosen strategy (below) ---
    # --- post-passes: quotes/captions if no native handling ---
    # --- stop at draft/preview, never publish ---
```

**Strategy 1 — HTML-paste (modern contenteditable, paste keeps fidelity).**
Reuse Habr's `_data_uri`, `_paste_html`, `_wait_for_image_uploads` verbatim (copy into this module). Body:

```python
    page.click(BODY_SEL)  # move caret into the body before pasting
    body_html = emit_body(
        doc, caption_marker=<per discovery>, max_heading_level=<per discovery>,
        image_src=lambda f: _data_uri(images_dir / f),  # if auto-upload works
    )
    _paste_html(page, body_html)  # selector inside _paste_html → BODY_SEL
    _wait_for_image_uploads(page, sum(isinstance(b, Image) for b in doc.blocks), log)
```
If images do NOT auto-upload from data-URIs, drop `image_src`, emit `[[IMG ...]]` markers, and add an explicit upload pass via the editor's `<input type=file>` (model on Pikabu's File-paste path — read `src/pikabu_adapter.py`).

**Strategy 2 — clipboard-paste (lossy paste).**
Model on `src/vc_adapter.py`: emit with `quote_as_paragraph=True` and the appropriate `img_sep`, paste via the real clipboard, then run restore passes (strong/em, quotes, images). Read the VC adapter before writing.

**Strategy 3 — markup/HTML source field (textarea / BBCode / Markdown).**
Emit the body and set the field value directly (`page.fill(BODY_SEL, body)` or `page.evaluate` to set `.value` + dispatch `input`). If BBCode/Markdown rather than HTML, add a small pure formatter (its own function, unit-tested like `test_vc_format_segments.py`) instead of `emit_body`'s HTML — or extend `emit_body` with a flag if the shape is close. Images uploaded via the editor's upload control / endpoint found in discovery.

**Post-passes** (only if no native handling, per discovery): copy Habr's `_convert_quotes` / `_set_captions` and retarget their selectors. If the engine has native quote/caption blocks reachable directly, prefer those.

**Stop** (wrap in try/except, like Habr):

```python
    STOP_BUTTON_TEXT = "<per discovery: Предпросмотр / Сохранить черновик>"
    log(f"Advancing to draft/preview: «{STOP_BUTTON_TEXT}»")
    try:
        page.locator(f"button:has-text('{STOP_BUTTON_TEXT}')").first.click(timeout=10000)
        log("Stopped at draft/preview. Review and publish manually.")
    except Exception as e:  # noqa: BLE001
        log(f"Could not click «{STOP_BUTTON_TEXT}» ({str(e)[:80]}); advance manually.")
```

**Step (tests):** If a new `emit_body` flag or a pure formatter was introduced, add a focused unit test (`tests/test_emit_html.py` or a new `tests/test_smartlab_*.py`) and run it green. If only existing flags are reused, no new emit tests.

Run: `python -m pytest -q`
Expected: PASS.

**Step (commit):**

```bash
git add src/smartlab_adapter.py tests/   # tests/ only if added
git commit -m "feat(smartlab): build_document — title + body + images + stop at draft"
```

---

## Phase 4 — End-to-end validation & finish

### Task 6: Manual end-to-end run (acceptance)

**Step 1:** Run: `! python cli.py layout <slug> <client> smartlab` on a real article in `in/`.

**Step 2:** In the opened draft/preview verify: title, bold/italic, bullet + ordered lists, quotes, images with captions render correctly — and that **nothing is published**.

**Step 3:** If anything is off, use superpowers:systematic-debugging, fix `build_document`, re-run. Update `docs/platform-notes.md` with any gotchas found (mirror VC/Habr "gotchas" notes).

**Step 4 (commit any fixes):**

```bash
git add src/smartlab_adapter.py docs/platform-notes.md
git commit -m "fix(smartlab): <gotcha addressed during e2e>"
```

### Task 7: Finish the branch

Run the full suite once more (`python -m pytest -q` → PASS), then use superpowers:finishing-a-development-branch to decide merge/PR. Update the project memory (`project_smartlab_adapter.md` + a line in `MEMORY.md`) to record the adapter as DONE with its engine/strategy, mirroring the Habr/Pikabu memory entries.

---

## Notes for the implementer
- **DRY:** reuse `emit_html.emit_body` and Habr/VC/Pikabu helpers — do not re-derive HTML emission. Copy a helper only when its selector/behavior genuinely differs.
- **YAGNI:** no tags/topic/publish handling in v1. Stop at draft/preview.
- **TDD** applies to the deterministic/pure parts (registry, any formatter). The browser-driving `build_document` is validated by the live run (Task 6), not mocked — matching the project's established line.
- **Never publish.** Every exit path stops at draft/preview and leaves the window open.

# Pikabu Browser Automation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Take a standard unpacked Google Docs zip (`in/<slug>/index.html` + `images/`) and, via Python + Playwright, fill the Pikabu post editor — images included — stopping at a point determined during discovery (draft, or just-before-publish). The user does the final publish.

**Architecture:** Reuse the existing platform-agnostic pipeline. The BeautifulSoup parser (`src/parser.py`) already turns messy GDoc HTML into the IR (`src/ir.py`: `Run / Heading / Paragraph / Image / ListBlock / Quote` + a `Document.title`). Pikabu is purely a **new adapter** (`src/pikabu_adapter.py`) over that same IR — a sibling of `src/vc_adapter.py`. Nothing in the parser, IR, or emitter changes.

**Tech Stack:** Python 3, Playwright (Chromium, persistent context). Parsing reuses the existing BeautifulSoup parser; no new test framework needed (the parser is already covered).

**Design doc:** `docs/plans/2026-05-29-pikabu-browser-automation-design.md`

---

## What is reused vs. new

**Reused unchanged (do NOT touch):**
- `src/parser.py` — GDoc HTML → `Document` IR.
- `src/ir.py` — `Run, Heading, Paragraph, Image, ListItem, ListBlock, Quote, Document`.
- `src/emit_html.py` — IR → clean body HTML (available if a paste-based path is chosen during discovery).
- `tests/` — parser unit tests; stay green, not modified.

**New (this plan):**
- `src/discover_pikabu.py` — manual discovery script (pause + checklist).
- `experiments/04-pikabu-editor/notes.md` — recorded discovery facts.
- `src/pikabu_adapter.py` — Playwright Pikabu automation (mirror of `src/vc_adapter.py`).
- `run_pikabu.py` — entry point (mirror of `run_vc.py`).
- `.pikabu-profile/` — persistent browser profile (gitignored, never committed).

**Reference — VC adapter shape to mirror** (`src/vc_adapter.py`):
- `_type_runs(page, runs)` — types text, toggling bold/italic via `Ctrl+B` / `Ctrl+I` per run. **Editor-agnostic — copy verbatim.**
- `build_document(page, doc, images_dir, log=print)` — the dispatch loop over `doc.blocks` (`Heading` → `_insert_heading`, `Paragraph` → `_type_runs`, `Image` → `_insert_image`, `ListBlock` → `_insert_list`, `Quote` → `_insert_quote`). **Skeleton copied; the `_insert_*` bodies are rewritten for Pikabu.**
- `run_document(images_dir, doc, keep_open=True)` — launches `launch_persistent_context`, grants clipboard perms, calls `build_document`, keeps the window open. **Mirror with the Pikabu profile dir.**

---

## Task 1: Setup — gitignore the Pikabu profile

**Files:**
- Modify: `.gitignore`

**Step 1: Add the Pikabu profile dir to `.gitignore`**

Append this line to `.gitignore` (next to the existing `.vc-profile/` entry):

```
.pikabu-profile/
```

**Step 2: Verify it is ignored**

Run: `git status --porcelain .pikabu-profile/ 2>$null; git check-ignore .pikabu-profile/`
Expected: `git check-ignore` echoes `.pikabu-profile/` (it is ignored). No tracked changes appear.

**Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore Pikabu browser profile"
```

---

## Task 2: Pikabu editor discovery (manual, exploratory — NOT TDD)

> This task produces recorded facts, not automated tests. The Pikabu editor DOM is unknown; do not guess selectors. Do this WITH the user — they log in by hand and help confirm selectors. Every `<fill>` in the notes must hold a real observed value before Task 3. This task also RESOLVES three deferred design decisions: supported blocks + degradation rules, inline-format mechanism, and the stop point (draft vs. before-publish + how tags/community/flags are handled).

**Files:**
- Create: `src/discover_pikabu.py`
- Create: `experiments/04-pikabu-editor/notes.md`

**Step 1: Create the notes template**

```markdown
# Experiment 04 — Pikabu editor discovery

**Date:** <fill>
**Goal:** record real selectors, the working text-insert mechanism, the set of
supported blocks (+ degradation rules), and the stop point — before writing the
adapter.

## New-post navigation
- URL of the "new post" page: <fill>
- How to detect logged-out state (selector/text): <fill>
- Is there a draft concept? How is a saved draft detected (URL / toast / indicator): <fill>

## Selectors
- Title field: <fill>
- Body editor container (contenteditable / textarea / block editor?): <fill>
- Image-insert control (button / "+" / drag zone): <fill>
- Hidden file input for image upload: <fill>
- Caption field on an inserted image block (if any): <fill>

## Supported blocks + degradation rules (we bring the full VC set)
- Headings (H2)? supported / NO -> degrade to: <fill, e.g. bold paragraph>
- Bold / italic inline? supported via Ctrl+B / Ctrl+I / other / NO: <fill>
- Unordered list? supported / NO -> degrade to: <fill>
- Ordered list? supported / NO -> degrade to: <fill, e.g. "1. " text prefix>
- Quote / blockquote? supported / NO -> degrade to: <fill>
- Image caption? supported / NO -> degrade to: <fill, e.g. italic paragraph under image>

## Text-insert mechanism (pick the one that works)
- [ ] per-block typing via keyboard (like VC adapter): type runs, Enter between blocks
- [ ] paste clean HTML (emit_html.emit_body) via clipboard + Ctrl+V
- [ ] paste via dispatched `paste` event with DataTransfer(text/html)
- Notes on what survives a paste (h2, bold, em, lists): <fill>

## Image upload
- After set_input_files on the file input, does a real image block appear? <fill>
- Is upload async (must wait for the <img> to finish loading, like VC)? <fill>
- Where/how is the caption entered for that block (if supported)? <fill>

## Required fields + stop point  (RESOLVES design open question)
- Tags: required? where/how entered? <fill>
- Community / section: required? how chosen? <fill>
- Flags (18+, authored, etc.): required? <fill>
- DECISION — where the adapter stops: <draft saved | filled up to before "Publish" | other>
- DECISION — which required fields (if any) the adapter fills vs. leaves to the user: <fill>
```

**Step 2: Write the discovery script**

Mirror `src/discover_vc.py` (use it as the reference for launch + pause):

```python
# src/discover_pikabu.py
"""Open Pikabu in a persistent, visible browser and pause for manual inspection.

Usage: python -m src.discover_pikabu
Log in by hand if prompted, navigate to the new-post page, then use DevTools to
record selectors into experiments/04-pikabu-editor/notes.md. Press Enter in the
terminal to close. Cookies persist in .pikabu-profile/ for later runs.
"""
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
PIKABU_URL = "https://pikabu.ru/"  # confirm exact new-post URL during discovery


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(PIKABU_URL)
        input("Inspect Pikabu, record selectors. Press Enter here to close...\n")
        ctx.close()


if __name__ == "__main__":
    main()
```

**Step 3: Run it and inspect WITH the user**

Run: `python -m src.discover_pikabu`
Expected: a visible Chromium opens on Pikabu. The user logs in once (cookies persist in `.pikabu-profile/`). Together, fill every `<fill>` in `notes.md`. Concretely confirm, in the open browser:
- the new-post URL and title/body selectors,
- whether `Ctrl+B`/`Ctrl+I` toggle bold/italic in the body,
- which of the listed blocks the editor offers (and pick a degradation for each missing one),
- one `image1.png` upload via the file input (does a block appear? is it async?),
- the required fields and the chosen **stop point**.

**Step 4: Commit the recorded findings**

```bash
git add src/discover_pikabu.py experiments/04-pikabu-editor/notes.md
git commit -m "experiment(04): Pikabu editor discovery — selectors, blocks, stop point"
```

---

## Task 3: Pikabu adapter (manual validation loop — NOT TDD)

> Browser automation is verified by running it and inspecting the result, not by unit tests. Use the selectors / mechanism / degradation rules recorded in Task 2. Build incrementally and commit after each working sub-step. Copy `_type_runs` and the `build_document` dispatch skeleton from `src/vc_adapter.py` verbatim; rewrite each `_insert_*` against Pikabu facts. Mark any not-yet-confirmed selector with `# DISCOVERY:` and replace it with the recorded value.

**Files:**
- Create: `src/pikabu_adapter.py`

**Step 1: Skeleton — launch persistent context, open the new-post page**

Start from this skeleton (constants filled from Task 2). Keep the module docstring listing the recorded selectors, as `vc_adapter.py` does.

```python
# src/pikabu_adapter.py
"""Drive the Pikabu post editor to build a post from a parsed Document.

Selectors recorded in experiments/04-pikabu-editor/notes.md:
- Title field:    # DISCOVERY
- Body container: # DISCOVERY
- Image insert:   # DISCOVERY
- File input:     # DISCOVERY
- Caption field:  # DISCOVERY

Visible browser, persistent profile, STOPS at the point chosen in discovery
(never auto-publishes unless discovery proved that is the only viable stop).
"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from src.ir import Heading, Paragraph, Image, ListBlock, Quote

PROFILE_DIR = ".pikabu-profile"
NEW_POST_URL = "https://pikabu.ru/"  # DISCOVERY: exact new-post URL
TITLE_SEL = "<fill>"  # DISCOVERY
BODY_SEL = "<fill>"   # DISCOVERY


def _type_runs(page, runs):
    """Type runs, toggling bold/italic per run. Copied from vc_adapter.

    If discovery showed Pikabu does NOT support inline bold/italic, drop the
    Ctrl+B / Ctrl+I presses and just type r.text (degradation rule from notes).
    """
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


def run_document(images_dir: Path, doc, keep_open=True):
    """Launch a visible, authenticated browser and build the post. Stops there."""
    images_dir = Path(images_dir)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        build_document(page, doc, images_dir)
        print("Done — post built. Review it in the browser and publish manually.")
        if keep_open:
            try:
                input("Press Enter here to close the browser...")
            except EOFError:
                time.sleep(15)
        ctx.close()
```

Add a minimal `build_document` that only navigates + sets the title for now:

```python
def build_document(page, doc, images_dir: Path, log=print):
    log(f"Opening editor: {NEW_POST_URL}")
    page.goto(NEW_POST_URL)
    # DISCOVERY: if a logged-out marker is present, pause for manual login.
    page.wait_for_selector(TITLE_SEL, timeout=30000)
    time.sleep(2)
    log(f"Title: {doc.title!r}")
    page.click(TITLE_SEL)
    page.keyboard.type(doc.title)
```

Run: `python -c "from pathlib import Path; from src.parser import parse; from src.pikabu_adapter import run_document; d=parse(Path('example/lists-quotes/index.html').read_text(encoding='utf-8')); run_document(Path('example/lists-quotes/images'), d)"`
Expected: visible browser opens the new-post editor (after manual login on first run) and the title is typed. Commit:
```bash
git add src/pikabu_adapter.py
git commit -m "feat(pikabu): launch persistent context, open editor, set title"
```

**Step 2: Paragraphs + the dispatch loop.** Copy the `build_document` block-dispatch loop from `vc_adapter.py`. Wire `Paragraph` → `_type_runs` and the inter-block Enter handling. Run on `example/lists-quotes`; verify paragraphs land in order with correct bold/italic (or plain text if discovery said no inline formatting). Commit `feat(pikabu): paragraphs and block dispatch loop`.

**Step 3: Headings.** Add `_insert_heading(page, runs)` using the recorded heading control — or, per the degradation rule, emit a bold paragraph if Pikabu lacks headings. Verify H2s. Commit `feat(pikabu): headings (or degraded bold paragraphs)`.

**Step 4: Images + captions.** Add `_insert_image(page, image_path, caption_runs)`: trigger the image-insert control, `set_input_files` the hidden file input with `images_dir/<file>`, and — mirroring VC — **wait for the upload to finish** (a new `<img>` with a loaded `http(s)` src) before continuing, so block order isn't scrambled in image-dense regions. Fill the caption if the editor supports one (else apply the caption degradation rule). Validate the image exists on disk first (mirror VC's missing-image pause). Verify on `example/lists-quotes` (10 images). Commit `feat(pikabu): upload images with captions`.

**Step 5: Lists.** Add `_insert_list(page, list_block, is_last)`: if Pikabu has list blocks, build items (Enter between `<li>`) and set ordered/unordered per `list_block.ordered`; otherwise apply the degradation rule from notes (e.g. one paragraph per item, ordered items prefixed `"1. "`, `"2. "`, …). Verify both list kinds. Commit `feat(pikabu): lists (or degraded paragraphs)`.

**Step 6: Quotes.** Add `_insert_quote(page, quote, is_last)`: if Pikabu has a quote block, insert it and type the runs; otherwise apply the degradation rule (e.g. an italic paragraph, or `"> "`-prefixed text). Verify. Commit `feat(pikabu): quotes (or degraded paragraphs)`.

**Step 7: Stop point.** Implement the stop chosen in Task 2 — detect the saved draft (URL/indicator) and print it, or fill required fields up to just before "Publish" and stop. Never click the final publish unless discovery proved it's the only viable stop. Leave the window open. Commit `feat(pikabu): stop at the discovered stop point`.

**Validation loop (per design):** run on `example/lists-quotes` (and later a real `in/<slug>/`), inspect the Pikabu result, change ONE thing at a time, re-run, repeat until clean. Record deltas and any selector fixes in `experiments/04-pikabu-editor/notes.md`. Stabilize across 2–3 articles.

**Note on robustness:** the VC adapter accumulated hard-won fixes (real-click to re-anchor the toolbar after custom blocks, waiting for async image load, targeting the *last* matching block when several match a selector). Watch for the Pikabu equivalents during the loop; copy the *pattern*, not the VC selectors.

---

## Task 4: Entry point

**Files:**
- Create: `run_pikabu.py`

**Step 1: Write the entry point** (mirror of `run_vc.py`)

```python
# run_pikabu.py
"""Usage: python run_pikabu.py in/<slug>

Parses the unpacked Google Docs export in the given folder and drives the
Pikabu editor. The browser stays open for manual review/publishing.
"""
import sys
from pathlib import Path

from src.parser import parse
from src import pikabu_adapter


def main():
    if len(sys.argv) != 2:
        print("Usage: python run_pikabu.py in/<slug>")
        raise SystemExit(2)
    slug_dir = Path(sys.argv[1])
    index = slug_dir / "index.html"
    if not index.exists():
        print(f"Not found: {index}")
        raise SystemExit(1)

    doc = parse(index.read_text(encoding="utf-8"))
    referenced = [b.file for b in doc.blocks if hasattr(b, "file")]
    images_dir = slug_dir / "images"
    on_disk = {p.name for p in images_dir.glob("*")} if images_dir.exists() else set()
    missing = [f for f in referenced if f not in on_disk]
    if missing:
        print(f"WARNING: referenced images not found in {images_dir}: {missing}")

    print(f"Parsed: title={doc.title!r}, blocks={len(doc.blocks)}, images={len(referenced)}")
    pikabu_adapter.run_document(images_dir, doc)


if __name__ == "__main__":
    main()
```

**Step 2: Smoke test the parse path without the browser**

Run: `python -c "from pathlib import Path; from src.parser import parse; d=parse(Path('example/lists-quotes/index.html').read_text(encoding='utf-8')); print(d.title, len(d.blocks))"`
Expected: prints the title and a block count > 0 (confirms the shared parser still works; no Pikabu code involved).

**Step 3: Full run against the example**

Run: `python run_pikabu.py example/lists-quotes`
Expected: parse summary prints; visible browser opens; the post is built to the discovered stop point; window stays open.

**Step 4: Commit**

```bash
git add run_pikabu.py
git commit -m "feat: run_pikabu.py entry point wiring parser -> Pikabu adapter"
```

---

## Done criteria

- `python -m pytest -q` is still green (shared parser/emitter untouched).
- `experiments/04-pikabu-editor/notes.md` has no remaining `<fill>` placeholders, and records the supported-blocks/degradation rules and the chosen stop point.
- `python run_pikabu.py example/lists-quotes` builds a Pikabu post whose text, formatting, images, captions, lists, and quotes match the source (degraded blocks behaving per the recorded rules), verified by eye in the validation loop.

## Out of scope (per design)

API posting; a unified CLI wrapper; extracting a shared adapter base (do that only when a 3rd platform arrives — rule of three); other platforms (Dzen/Habr/Smartlab). The IR already accepts them.

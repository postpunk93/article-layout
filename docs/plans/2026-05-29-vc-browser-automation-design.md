# VC Browser Automation — Design

**Date:** 2026-05-29
**Status:** approved by user, ready to plan
**Supersedes the transport approach of:** `2026-05-25-article-layout-design.md`

## Why this pivot

The manual copy-paste path is abandoned. Experiment 01 (data URI) failed — VC strips `data:` URIs. Pasting from a browser-opened export also drops images (relative paths break in clipboard HTML). Useful side finding from experiment 01: **text and structure survive a paste into VC** (h1, p, figure, figcaption were preserved) — only the image bytes were lost.

New direction: **browser automation** that drives the VC editor directly. The script uploads image files through the editor's native file uploader, sidestepping the clipboard-image problem entirely.

## Goal

Take a standard unpacked Google Docs zip (`index.html` + `images/`), and via a Python + Playwright script transfer it into the VC.ru editor and **save a draft**. The script stops at the saved draft; the user reviews and publishes manually.

Eventually many platforms (VC, Dzen, Habr, Smartlab, others). **Start with VC only.**

## Fixed decisions

| Decision | Choice |
|---|---|
| Auth | Saved browser profile (persistent context). User logs in by hand once; cookies persist and are reused. No password stored. |
| Stack | Python + Playwright (automation) + BeautifulSoup (HTML parsing). |
| Run mode | Visible (headed) browser. Script fills the editor, saves the draft, and stops. User publishes manually. |
| Content insertion | Hybrid A+B: paste the text body in one shot, then upload images into their slots via the native file input; fall back to per-block typing on problem blocks. |
| v1 block scope | h1/h2 headings, paragraphs, bold/italic, images with captions. |

## Architecture & data flow

Three independent layers so future platforms become new adapters without touching parsing:

```
in/<slug>/index.html + images/   (standard unpacked GDoc zip)
        │
        ▼
[1] Parser (BeautifulSoup)  →  strips GDoc cruft, merges spans
        │
        ▼
[2] IR — intermediate block model (platform-agnostic list)
        │  heading(level, runs) · paragraph(runs) · image(file, caption?)
        │  run = {text, bold, italic}
        ▼
[3] VC adapter (Playwright, persistent profile, visible browser)
        │  paste text body  →  upload images into slots  →  stop at draft
        ▼
   Saved draft in VC (user publishes manually)
```

The **IR in the middle** is the key idea: the parser knows nothing about VC; the adapter knows nothing about GDoc. A new platform needs only a new adapter reading the same IR.

## Parser & IR

**Input shape:** GDoc export is a flat sequence of `<h1>/<h2>/<p>`; text is fragmented across many `<span>` with `.cN` classes; styles are declared in `<style>` in `<head>`.

**Parser steps:**

1. **Read the stylesheet** — from `<style>`, determine which `.cN` classes mean `font-style: italic` and which mean `font-weight: 700` (bold). Store as class sets.
2. **Walk body blocks** (`h1`, `h2`, `p`) in order.
3. **Merge spans into runs** — adjacent spans with the same effective style become one run `{text, bold, italic}`. Decode HTML entities.
4. **Classify the block:**
   - `<h1>` → the first one becomes the **VC entry title** (separate field), not a body block.
   - `<h2>` → `heading(level=2)`.
   - `<p>` containing `<img>` → `image(file=imageN.png)`.
   - `<p>` with text → `paragraph(runs)`.
5. **Caption rule (user-confirmed):** for the text immediately following an image (after a `<br>` in the same `<p>`, or in the next `<p>`): if it is **entirely italic** → it is the image `caption`, attached to the image and NOT emitted as a separate paragraph. If it is not italic (or absent) → the image has no caption and the text stays a standalone `paragraph`. (This supersedes the earlier `<br>`-position hypothesis — we key off italic.)
6. **Drop empty blocks** (`<p></p>`, `<p><span></span></p>`).

**Resulting IR** (title stored separately from the block list):

```
[ heading(2, [run("Раздел", bold=false)]),
  paragraph([run("Обычный ", false,false), run("курсив", false,true), run(" дальше", false,false)]),
  image("image5.png", caption=[run("Это я", italic=true)]),
  image("image6.png", caption=None) ]
```

Covered by unit tests on `example/` (deterministic, no browser needed).

## VC adapter (Playwright)

**Browser launch:**
- `launch_persistent_context(user_data_dir="./.vc-profile", headless=False)` — visible window, session lives in the profile folder (gitignored).
- First run: if a "log in" state is detected → script pauses and waits for the user to log in by hand, then continues. Cookies are reused afterward.

**Sequence for one article:**

1. Navigate to the new-entry page (URL/button fixed during discovery).
2. **Title** — type the first `<h1>` from IR into the title field.
3. **Text body** — build clean HTML from IR **without images**: headings, paragraphs, bold/italic. At each image position leave a visible placeholder marker like `[[IMG:image5.png]]`. Paste the whole HTML in one shot (paste mechanism — clipboard API or dispatched paste event — chosen during discovery).
4. **Images** — for each marker in order: place the cursor on it → trigger the editor's native image upload (set the file `in/<slug>/images/imageN.png` on the hidden `<input type=file>`) → wait for the image block to appear → fill the caption if present in IR → remove the text marker.
5. **Wait for the draft to autosave** (or click save); confirm a draft was created.
6. **Stop.** Window stays open; user reviews and publishes manually.

**Why:** paste reliably carries text and formatting into VC (proven by experiment 01) but strips image bytes — so images go via the editor's own file-upload path. Markers guarantee correct order and position.

**Brittleness note:** the marker path (steps 3–4) is the main hypothesis the discovery phase validates. If marker insertion / cursor positioning in the VC editor proves unreliable, fall back to pure variant A for the body (per-block typing), keeping the same image-upload method.

## Discovery phase (done first, with the user)

Replace DOM guesses with recorded facts. A discovery script `src/discover_vc.py` opens the persistent browser on the new-entry page and **pauses**. With the user's help, verify against a checklist and record into `experiments/03-vc-editor/notes.md`:

1. **Selectors:** title field, body container, image-insert button / "+", hidden `<input type=file>`.
2. **Text paste:** which mechanism actually works — clipboard write via `context.grant_permissions(["clipboard-write"])` + Ctrl+V, or dispatching a `paste` event with `DataTransfer(text/html)`. Test on a snippet with h2 + paragraph + bold/italic.
3. **Image upload:** upload `image5.png` via the file input; confirm a real image block appears; find where the caption is entered.
4. **Markers:** paste text containing `[[IMG:...]]`; check whether markers survive the paste and whether the cursor can be placed on them for replacement.
5. **URL/navigation:** exact new-entry page address and how to detect the draft was saved.

Output: a filled `notes.md` with selectors and the confirmed mechanism. Only then is the adapter written.

## Project structure (additions)

```
src/
├── parser.py          # GDoc HTML → IR (BeautifulSoup)
├── ir.py              # dataclasses: Heading, Paragraph, Image, Run + title
├── emit_html.py       # IR → clean body HTML with [[IMG:...]] markers
├── discover_vc.py     # discovery script (pause + checklist)
└── vc_adapter.py      # Playwright VC automation
run_vc.py              # entry point: python run_vc.py in/<slug>
tests/
└── test_parser.py     # parser unit tests on example/
experiments/03-vc-editor/notes.md   # discovery result
.vc-profile/           # persistent profile (gitignored)
requirements.txt       # playwright, beautifulsoup4, pytest
```

## Error handling

- Visible browser + "fail loudly": on any unexpected state (selector missing, not logged in, image not uploaded) — pause with a clear console message; window stays open for inspection. No silent skips.
- Validate images against the file list in `images/`: if marker count ≠ file count → stop with a warning.
- The script never publishes — draft only.

## Testing

- **Parser** — unit tests on `example/` (deterministic, no browser): run merging, caption rule (italic → caption), splitting entry title from body.
- **Adapter** — verified manually via the project's validation loop: one run → inspect the VC draft → one change at a time → repeat until clean.

## Boundaries of v1 (YAGNI)

- VC only. Only h1/h2, paragraphs, bold/italic, images with captions.
- No: lists, tables, code, Google link wrappers, embeds, quotes (yellow highlight) — added when a real article needs them.
- No API posting, no CLI wrapper, no other platforms — but the IR is already shaped to accept them.

## Open questions (do not block start)

- Exact VC paste mechanism and selectors — resolved by the discovery phase.
- Whether markers survive paste, or we fall back to per-block typing — resolved by discovery.
- Quote / highlight mapping — deferred until a real article with highlights appears.
- Other platforms' adapters (Dzen, Habr, Smartlab) — future phases on top of the same IR.

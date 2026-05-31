# Habr adapter — design

Date: 2026-05-31
Branch: `feat/habr-adapter`

Third platform adapter, alongside VC (Editor.js) and Pikabu (Tiptap). Lays out a
GDoc-sourced article into Habr's visual article editor and stops on the
article-settings screen for manual completion. Never publishes.

## Goal & scope (v1)

- Lay out the article **body** into Habr's visual editor: title (h1), blocks,
  images, captions.
- Then click **«Далее в настройки»** and **stop on the article-settings screen**
  (hubs / target audience / keywords NOT filled — the editor blocks save until
  they are; that's fine, we leave the window open for manual completion).
- **Out of scope (backlog):** filling hubs/tags/audience/keywords; "кат" (cut);
  publishing.

## Key constraints (confirmed with the user)

- **Visual editor, by analogy with VC/Pikabu** — not the Markdown/HTML source mode.
- **Paste is high-fidelity**: manual paste pulls in everything including images
  (richer than VC, which strips images, and Pikabu, which needs a File paste).
  Caveat: the user's manual success pasted from the **Google Doc** (bitmaps on the
  clipboard). Our pipeline rebuilds from IR + local image files, so image
  transport for *our generated HTML* is still an open item the discovery probe
  must resolve.
- **One subheading level only.** h1 = article title, h2 = subheadings.
  **h3 (and deeper) → bold text on its own line** (`<p><strong>…</strong></p>`),
  not a real heading.
- Two post-passes are the expected manual gap to automate: **quotes** (paste does
  not make a paragraph a quote) and **captions** (move the caption text from the
  body into the image's native caption field).

## Architecture & integration

Habr slots in under the existing adapter contract — no changes to `cli.py`,
`orchestrator.py`, or `sessions.is_alive`.

- **New file** `src/habr_adapter.py`, exporting:
  - `EDITOR_URL` — sandbox editor URL (exact value from discovery),
  - `TITLE_SEL` / `BODY_SEL` — selectors; one becomes the alive-marker,
  - `build_document(page, doc, images_dir)` — entry point, same signature as the
    other adapters.
- **Registration:** one `"habr": {...}` entry in `sessions.PLATFORMS`
  (`build_document`, `editor_url`, `alive_marker`), plus the import next to
  `vc_adapter, pikabu_adapter`.
- After that, `python cli.py login <client> habr`, `status`, and
  `layout <slug> <client> habr` (or `all`) work automatically —
  `parse_platforms` picks up `habr` from `known_platforms()`.

Files touched: `src/habr_adapter.py` (new), `src/sessions.py` (import + entry),
`src/emit_html.py` (h3→bold rule), `tests/test_habr_*.py` (new).

## Discovery phase (one-off probe on the sandbox)

Run a throwaway probe on a logged-in sandbox profile (per the onboarding pattern
in `docs/platform-notes.md`; the script is removed afterward, findings recorded).
It must answer:

1. **Navigation & auth** — exact sandbox editor URL; the logged-in-only selector
   (alive-marker candidate); whether/how the draft autosaves.
2. **Editor engine & selectors** — framework (ProseMirror / contenteditable /
   other); title (h1) and body selectors; stable `data-test`/attributes vs
   drifting css-module hashes.
3. **Fidelity of OUR HTML** — paste a sample covering every block (h2, paragraphs,
   bold/italic, ul/ol, quote) from our `emit_body` (not from a GDoc); record what
   survives.
4. **Image transport (main risk)** — paste an image as `<img src=data-URI>` and as
   `<img src=file/https>`; does Habr upload it to habrastorage itself (wait for an
   `https` src) or strip it? Determines whether images are "free" on paste or need
   a marker-replace + File-paste pass (Pikabu model).
5. **Quote block & caption field** — structure of the native quote block (for the
   conversion pass); whether images have a native caption field (target for moving
   the caption out of the body).
6. **Stop point** — the «черновик → настройка статьи» flow: the button/selector to
   reach settings, and a marker selector for the settings screen (success signal).

Findings are appended to `docs/platform-notes.md` (new "Habr" section) before the
adapter is written.

## Body transport & emit changes

**Body = one high-fidelity paste (Pikabu model).** Habr keeps formatting, so the
body is pasted in a single pass, not block-by-block (the VC fallback). The exact
paste mechanism (synthetic `ClipboardEvent` with `text/html`, à la Pikabu, vs the
real OS clipboard, à la VC) is confirmed in discovery and we use whichever works.

`build_document` sequence:
1. Open the sandbox editor, wait for `BODY_SEL`.
2. Type the title (h1) into the title field.
3. Paste the body from `emit_body(doc, …)` in one paste.
4. Run post-passes (images → quotes → captions).
5. Click «Далее в настройки» and stop on the settings screen.

**`emit_html.py` — heading degradation rule.** Habr has a single subheading level
(h2). Add a parameter, e.g. `max_heading_level=2` (default keeps current behavior;
VC/Pikabu untouched):

- `Heading(level=2)` → `<h2>` as today.
- `Heading(level>=3)` → a bold-run paragraph `<p><strong>…</strong></p>` ("bold on
  one line"), not `<h3>`.

Images stay as `[[IMG…]]` markers (+ caption) in the body; the final form (marker +
replace vs direct `<img>`) is chosen from the image-transport discovery result.
Quotes are emitted so the post-pass can find and convert them (likely
`quote_as_paragraph=True` as in VC, or `<blockquote>` if Habr preserves it —
discovery decides).

## Post-passes (best-effort, isolated; order: images → quotes → captions)

**1. Images** — per discovery:
- *Good case:* Habr uploads images straight from the pasted HTML → no pass needed;
  only wait for the `https` habrastorage src before continuing.
- *Fallback:* Habr strips them → replace each `[[IMG file]]` marker with a native
  upload (paste a real `File` built from the local bytes, Pikabu model, or the file
  chooser), wait for the final `https` src (async upload).

**2. Quotes** — paste does not make a paragraph a quote. Locate each quote (by
text/marker from the IR) and convert it to the native quote block; exact mechanism
(toolbar button on selection vs block re-creation) fixed by discovery.

**3. Captions** — the caption sits as a separate paragraph under the image in the
body. For each image: take the caption text from the IR, move it into the image's
native caption field, delete the original caption paragraph. (If Habr has no native
caption field, leave the caption paragraph under the image and log it — discovery,
item 5.)

**Block-count check** (as in VC): after paste, compare the body block count to the
IR block count; on mismatch, log a warning and skip passes that rely on exact block
correspondence (images still run, matched by marker content). Each item is
best-effort — one failure cannot abort the run.

## Stop point & draft flow

Habr is two-stage: **editor (body) → article-settings screen** (hubs / audience /
keywords, required to save/publish). v1 lays out the body, clicks **«Далее в
настройки»**, and stops on the settings screen.

- The settings navigation click is the last action of `build_document`; the exact
  selector/text comes from discovery (item 6).
- **Success signal = reached the settings screen** (its marker selector appears)
  with the body laid out (title set, block count reconciled, images carry `https`
  srcs). We do not fill any settings field and never publish.
- `cmd_layout` already leaves the window open (catches exceptions, then
  `input("Press Enter to close…")`) — no orchestrator change needed.
- The alive-marker for `is_alive` is the title/body selector visible only to a
  logged-in user; taken from discovery, stored in `sessions.PLATFORMS["habr"]`.

## Error handling

- Post-passes are best-effort and isolated — a failing quote/image/caption is
  logged and does not abort the run.
- Block-count mismatch → warning + skip of block-dependent passes (images matched
  by marker run anyway).
- Image upload → mandatory wait for the `https` src; timeout logged, run continues.
- A top-level exception is caught by `cmd_layout`; the window stays open and the
  summary shows `FAILED habr: …` — no orchestrator change.

## Testing

- **Unit, no browser** — `tests/test_habr_emit.py`: the h2 / h3→bold rule in
  `emit_html`; body/marker emission. Deterministic.
- **Unit adapter logic** — any pure helpers (caption-to-image matching, block
  parsing) tested against fakes, like `format_segments` / `_select_range` in VC.
- **End-to-end manual** on the sandbox with a real `in/` article (lists, quotes,
  images+captions, an h3): acceptance = body laid out, h3 bold, images in
  habrastorage, native quotes, captions in image fields, stop on the settings
  screen. Record as "validated end-to-end", like VC/Pikabu.
- Selectors keyed to stable `data-test`/attributes, never css-module hashes
  (per the platform-notes warning).

## Selector-stability note

`data-test="…"` and similar stable attributes only; css-module hash suffixes drift
between deploys — match the stable prefix, never the full hashed class.

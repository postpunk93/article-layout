# Experiment 04 — Pikabu editor discovery

**Date:** 2026-05-29
**Status:** IN PROGRESS — most facts recorded; ONE open question (image upload).
**Editor:** Pikabu's post editor is **Tiptap / ProseMirror** (Vue-wrapped).

## TL;DR for resuming
- Title, body, formatting, headings, lists, quotes — all SOLVED.
- **HTML paste into Tiptap is high-fidelity** → the whole body can go in ONE paste
  (h2, p, b/i, ul, ol, li, blockquote all survive). This is the big win and lets
  the Pikabu adapter be much simpler than VC's block-by-block approach.
- **OPEN:** how to drive the image upload programmatically (floating "+" → photo
  button does not open a file chooser on an ElementHandle `.click()`). See
  "Image upload" below for what was tried and what to try next.

## New-post navigation
- URL of the "new post" page: **https://pikabu.ru/add**
- Logged-out detection: not yet observed (we were logged in). Likely a redirect to
  a login page / absence of `.tiptap.ProseMirror`. Confirm next session.
- Draft concept: YES. There is a **«Сохранить черновик»** button (gray, top of the
  right column). Publish button is `[data-test="story-publish"]` («Опубликовать пост»).
  Also «Предпросмотр» (preview). How a saved draft is detected (URL/toast): TBD.

## Selectors  (data-test attrs are STABLE; CSS-module hashes like `--astkN9TQ` may drift)
- Title field: `textarea[placeholder="Заголовок"]`  (class `title-view__content--astkN9TQ`)
- Body editor container: `.tiptap.ProseMirror`  (contenteditable=true)
- Formatting toolbar (selection/bubble menu) buttons, by stable `data-test`:
  - `[data-test="editor-ctrl-heading"]`  (single heading level; renders `<h2>`, node class `node-heading-first-view__host`)
  - `[data-test="editor-ctrl-bold"]`  /  `editor-ctrl-italic`  /  `editor-ctrl-strike`
  - `[data-test="editor-ctrl-link"]`
  - `[data-test="editor-ctrl-quote"]`   ← blockquote
  - `[data-test="editor-ctrl-highlight"]`  (text-block) , `editor-ctrl-marker` (highlight color), `editor-ctrl-spoiler`
  - `[data-test="editor-ctrl-ul"]`  ← bullet list
  - `[data-test="editor-ctrl-ol"]`  ← ordered list
  - `[data-test="editor-ctrl-dnd-start"]` (drag handle)
  - NOTE: these are `disabled` until there is a focus/selection; they act on the current block/selection.
- Floating "+" insert control (appears on an EMPTY line): `.floating-menu-view__button--HzqgG6Ir`
- Floating insert-menu media buttons: `.floating-menu-view__menuButton--MJpEPZAY`
  identified by their SVG icon `<use xlink:href>`:
  - `#icon--ui__photo_20`            → single image  ← what we want
  - `#icon--ui__ic_round-collections`→ gallery (multiple)
  - `#icon--ui__play_20`             → video
  - `#icon--ui__divider_20`          → divider
  - `#icon--ui__poll_circle_20`      → poll
- Tags input: `.pkb-input-tag__input--U63z_jON` (hashed)
- Publish settings (checkboxes), by `data-test`: `setting-nsfw` (18+), `setting-anonymous`,
  `setting-scheduled`, `setting-series`, `setting-my`.

## Supported blocks + degradation rules
- **ALL VC block types are supported natively — NO degradation needed.**
  Heading ✅, bold ✅, italic ✅, unordered list ✅, ordered list ✅, quote ✅.
- Image caption: TBD (depends on the image-upload result — see open question).

## Text-insert mechanism  → PASTE (high fidelity)
- Confirmed working: dispatch a synthetic paste event carrying `text/html`:
  ```js
  const dt = new DataTransfer();
  dt.setData('text/html', html);
  dt.setData('text/plain', 'fallback');
  el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles:true, cancelable:true}));
  ```
- Pasting `<h2>…<p>…<strong>…<em>…<ul><li>…<ol><li>…<blockquote>…` produced exactly:
  `h2:1, p:8(incl. wrappers), ul:1, ol:1, li:4, blockquote:1, b:1, i:1`.
  i.e. every block mapped to a real Tiptap node. (See `probe_paste.json`.)
- Keyboard formatting also works on typed text: `Ctrl+B`/`Ctrl+I` →
  `normal <b>bold</b> <i>italic</i>` (see `probe_report.json`). So VC's `_type_runs`
  would port unchanged IF we ever do per-block typing — but paste is preferred here.
- `emit_html.emit_body` already emits exactly this kind of clean HTML with
  `[[IMG:file]]` / `[[CAP:text]]` markers → reuse it for the paste.

## Image upload  ← ONLY OPEN QUESTION
- Path is: focus an empty line → click floating "+" (`.floating-menu-view__button--HzqgG6Ir`)
  → click the photo button (`.floating-menu-view__menuButton--MJpEPZAY` whose icon use
  href contains `photo`).
- TRIED and FAILED to capture an upload:
  - JS `el.click()` on the photo button: no file chooser (untrusted gesture — browsers
    block file dialogs from untrusted clicks).
  - Real Playwright `ElementHandle.click()` inside `page.expect_file_chooser(8000)`:
    timed out, NO file chooser fired (`probe_image3.json`, `photo_button_found=true`).
  - After the photo click: NO new `input[type=file]`, NO modal/dialog/dropzone, editor
    tail unchanged (`probe_image4.json`). So the click may not be reaching the handler,
    OR a secondary submenu/upload widget appears that we didn't capture.
- TO TRY NEXT SESSION (in order):
  1. Real mouse click by bounding box: `page.mouse.click(cx, cy)` on the photo button,
     wrapped in `expect_file_chooser(timeout=15000)`. Confirms whether a trusted click
     opens the native chooser.
  2. After clicking photo, dump ALL visible buttons WITH TEXT (a secondary popover may
     offer «Загрузить с устройства» / «По ссылке» / «Из моих»). The real upload trigger
     may be one level deeper.
  3. Try drag-and-drop / paste-image: dispatch a `paste` (or `drop`) event with a
     `DataTransfer` containing a `File` (image bytes) onto `.tiptap.ProseMirror`.
     Tiptap image extensions often accept pasted/dropped image Files and upload them.
  4. Watch network: capture the upload XHR endpoint when a manual drag-drop is done, to
     understand the contract.
- After upload works: find where the caption goes (figcaption / a contenteditable under
  the `<img>` node-wrapper) and how to set it.

## Required fields + stop point  (tentative — confirm next session)
- Draft exists → plan to **stop at a saved draft** via «Сохранить черновик», leaving
  tags / community / flags to the user (mirrors VC: build, don't publish).
- Tags appear required to PUBLISH (not necessarily to save a draft). Community has a
  default («Сообщество (по умолчанию)»). Confirm whether a draft saves with empty tags.

## Adapter design implication (revised, simpler than the plan's block-by-block)
1. Set title: `textarea[placeholder="Заголовок"]`.
2. Build body HTML via `emit_html.emit_body(doc)` (with `[[IMG:]]`/`[[CAP:]]` markers),
   paste it into `.tiptap.ProseMirror` in ONE shot (synthetic paste event above).
3. For each `[[IMG:file]]` marker in order: place caret on it → run the image-upload
   path (once solved) → set caption → remove the marker.
4. Save draft, stop. (Never auto-publish.)

## Probe scripts (in this folder, all non-interactive, reusable)
- `probe_add.py` — fields/buttons/file-inputs dump → console (mojibake; use JSON probes).
- `probe_interact.py` → `probe_report.json` — toolbar `data-test` map + Ctrl+B/I test.
- `probe_paste.py` → `probe_paste.json` — HTML paste fidelity (the key result).
- `probe_image.py` / `probe_image2.py` → floating-menu media buttons by icon.
- `probe_image3.py` / `probe_image4.py` — image-upload attempts (currently failing; see above).
- All reuse the authenticated `.pikabu-profile/`. Run e.g. `python experiments/04-pikabu-editor/probe_paste.py`.
- `discover_pikabu.py` (in `src/`) opens the editor and keeps the window open until you
  close it — used for the one-time manual login that seeds `.pikabu-profile/`.

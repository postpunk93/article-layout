# Experiment 04 — Pikabu editor discovery

**Date:** 2026-05-29
**Status:** ✅ COMPLETE — all questions solved; adapter built & validated end-to-end.
**Editor:** Pikabu's post editor is **Tiptap / ProseMirror** (Vue-wrapped).

## TL;DR for resuming
- Title, body, formatting, headings, lists, quotes — all SOLVED (high-fidelity paste).
- **Image upload SOLVED** — paste a real `File` (image bytes) onto the editor via a
  synthetic `paste` event; Tiptap intercepts it and uploads to `cs*.pikabu.ru`. The
  floating "+" → photo button is a dead end (a trusted bbox `page.mouse.click`
  fires NO file chooser, NO input[type=file], NO submenu, NO XHR — probe_image5).
  Paste-a-File works instead (probe_image6).
- **Image caption is NATIVE** — each image node has a `node-image-caption-view`
  (placeholder «Введите описание к изображению (не обязательно)»). Set it from the IR;
  no separate caption paragraph needed.
- **Draft save SOLVED** — click «Сохранить черновик»; fires `POST …/save_draft_post`
  → 200. `/add` never restores it (always a fresh post); the saved draft lives at
  **https://pikabu.ru/drafts** (confirmed persisted — probe_draft3).
- **Adapter built:** `src/pikabu_adapter.py` + `run_pikabu.py`. Validated on the full
  real article: 72 IR blocks → 72 editor blocks, 10 images uploaded, 2 captions
  matching IR, lists/quote/headings intact, no leftover markers, draft saved.

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

## Image upload  ← SOLVED (paste a File; the "+→photo" button is a dead end)
- **WINNING METHOD (probe_image6):** build a real `File` from the image bytes in the
  page and dispatch a synthetic `paste` carrying it onto `.tiptap.ProseMirror`:
  ```js
  const res  = await fetch('data:' + mime + ';base64,' + b64);
  const file = new File([await res.blob()], name, {type: mime});
  const dt = new DataTransfer(); dt.items.add(file);
  el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles:true, cancelable:true}));
  ```
  Tiptap's image extension intercepts the File, shows a `blob:` placeholder
  (`node-image-loader-view__image`), uploads it (GET `…/get-upload-file-token` then a
  POST), and swaps in the final `https://cs*.pikabu.ru/…jpg` src on
  `node-image-view__image` (with width/height). WAIT for that http(s) src before
  proceeding (upload is async).
- The floating "+" → photo button (`#icon--ui__photo_20`) is a DEAD END: a real
  trusted `page.mouse.click` on its bbox fires NO file chooser, NO `input[type=file]`
  (any frame), NO submenu, NO XHR (probe_image5). Don't pursue it.
- **Marker replacement:** body is pasted with `[[IMG:file]]` marker paragraphs; for
  each, select the marker `<p>`'s contents via a DOM Range, then paste the image File
  → ProseMirror replaces the selection in place. This leaves an EMPTY paragraph where
  the marker was (image is a block node) — delete it: caret to start of that empty
  para, press Backspace (merges into previous block). Match markers BY FILENAME, not
  position, and process top-to-bottom so the just-added image is always the last `img`.

## Image caption  ← SOLVED (native field)
- Structure: `node-image-view__host` › `figure.node-image-view__figure[contenteditable=false]`
  (the `<img>` + edit/delete controls) + sibling `div.node-image-caption-view__host`
  containing `div.node-image-caption-view__placeholder[contenteditable=false]` (the
  «Введите описание…» hint) and `div[data-node-view-content]` (the editable caption).
- **Setting it:** a programmatic DOM Range does NOT reliably sync to ProseMirror's
  selection (typed text lands elsewhere), and the empty caption is ~0-height so a
  locator click stalls. Instead compute the caption host's on-screen point and fire a
  REAL `page.mouse.click(x, y)`, then `keyboard.type`. CRITICAL: `scrollIntoView({block:'center'})`
  the caption first — in a long article it's off-screen and the viewport-relative click
  would miss (this exact bug left all captions empty on the first full-article run).

## Draft saving  ← SOLVED
- Button «Сохранить черновик» (also present: «Опубликовать пост» = `[data-test="story-publish"]`,
  and a char-counter button «N/10…»). Clicking it fires `POST …/save_draft_post` → 200;
  wait on that response as the success signal (URL never changes).
- `/add` ALWAYS opens a fresh post (does not restore). The saved draft persists at
  **https://pikabu.ru/drafts** (verified: the draft's marker text is present there).
  Adapter stops here (never publishes), browser left open for review.

## Required fields + stop point
- Stop at a **saved draft** via «Сохранить черновик» (confirmed it persists with EMPTY
  tags/community — no fields required to SAVE). Tags/community are left to the user;
  they appear required only to PUBLISH. Community default: «Сообщество (по умолчанию)».

## Adapter design (as built — `src/pikabu_adapter.py`)
1. Set title: `page.click('textarea[placeholder="Заголовок"]')` then `keyboard.type`.
2. Body in ONE high-fidelity paste: `emit_body(doc, caption_marker=False)` → synthetic
   `paste` of `text/html` onto `.tiptap.ProseMirror`. No CAP markers (caption is native).
3. For each `Image` block, in order, matched by filename:
   - select its `[[IMG:file]]` marker `<p>` contents (DOM Range);
   - paste the image File (uploads), wait for the http(s) src;
   - if it has a caption, scroll the caption host into view + real `mouse.click` + type;
   - delete the leftover empty marker paragraph (Backspace).
4. Click «Сохранить черновик», wait for `save_draft_post`, stop. (Never publishes.)
- Run it: `python run_pikabu.py in/<slug>` (mirrors `run_vc.py`).

## Probe scripts (in this folder, all non-interactive, reusable)
- `probe_add.py` — fields/buttons/file-inputs dump → console (mojibake; use JSON probes).
- `probe_interact.py` → `probe_report.json` — toolbar `data-test` map + Ctrl+B/I test.
- `probe_paste.py` → `probe_paste.json` — HTML paste fidelity (the key result).
- `probe_image.py` / `probe_image2.py` → floating-menu media buttons by icon.
- `probe_image3.py` / `probe_image4.py` — FAILED "+→photo" button attempts (dead end).
- `probe_image5.py` → `probe_image5.json` — trusted bbox click on photo button: still
  no chooser/input/submenu/XHR (confirms the button is a dead end).
- `probe_image6.py` → `probe_image6.json` — **paste-a-File uploads** (the solution).
- `probe_image7.py` → `probe_image7.json` — marker replacement + caption-field discovery.
- `probe_draft.py` / `probe_draft2.py` / `probe_draft3.py` — draft save: endpoint, no
  /add restore, persists at `/drafts`.
- `verify_adapter.py` → `verify_adapter.json` — full adapter end-to-end check; dumps the
  editor block structure. No arg = small synthetic doc; `in/<slug>` arg = real article.
- All reuse the authenticated `.pikabu-profile/`. Run e.g. `python experiments/04-pikabu-editor/probe_paste.py`
  (the src-importing ones need `PYTHONPATH=.`, e.g. `PYTHONPATH=. python …/verify_adapter.py in/lists-quotes`).
- `discover_pikabu.py` (in `src/`) opens the editor and keeps the window open until you
  close it — used for the one-time manual login that seeds `.pikabu-profile/`.

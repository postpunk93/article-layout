# Platform notes (VC + Pikabu)

Consolidated, durable findings from the platform-discovery experiments (the one-off
probe scripts that produced these have been removed; their history is in git). This
is the reference for maintaining the adapters and for onboarding a new platform.

> **Selector stability:** `data-test="…"` attributes are stable. CSS-module hash
> suffixes (e.g. `--astkN9TQ`, `--HzqgG6Ir`) DRIFT between deploys — match on the
> stable prefix/`data-test`, never the full hashed class.

---

## Image transport — what works

- **Data-URI paste: dead end.** VC's paste handler strips `data:` image src. The
  surrounding structure (h1/p/figure/figcaption) survives, but image bytes are lost.
- **Localhost-served `<img src>`: not used.** Superseded before adoption.
- **Working methods are platform-native:** VC uploads via the editor's file chooser;
  Pikabu uploads by pasting a real `File` (see each section). Both upload to the
  platform's own CDN and the adapter waits for the real `https` src before continuing.

---

## VC — Editor.js (Codex Editor)

VC's post editor is an **Editor.js** instance: the body is a block model, not one
contenteditable. Heading levels are encoded in a class (`editor-header-tool--h2` /
`--h3`), NOT in semantic `<h2>/<h3>` tags.

### Navigation & auth
- Open the editor directly: `https://vc.ru/?modal=editor` (the new-post modal).
- Auth persists in the `.profiles/<client>/vc/` persistent context after a one-time
  manual login (`python cli.py login <client> vc`).
- Draft autosaves: once body content exists, the URL gains `&action=edit&id=<NNN>`.
  Detect a saved draft by waiting for `id=` in the URL.

### Confirmed selectors
- **Title**: `div.editor-tool-input[data-placeholder="Заголовок"]` (contenteditable).
- **Body root**: `.codex-editor`; blocks are `.ce-block`; a paragraph's editable is
  `.editor-text-tool`.
- **Add-block "+"**: `.ce-toolbar__plus` — only clickable when the current block is
  EMPTY (create one with Enter first). After a custom block it may report "not
  visible"; fall back to a JS click: `eval_on_selector('.ce-toolbar__plus','el=>el.click()')`.
- **Toolbox popover**: `.ce-popover.ce-toolbox.opened`; items are
  `li.ce-toolbox__item[data-type="…"]`. Order: `text`, `header` (H2), `header` (H3),
  `media` (image), `andropov` (link embed), `quote`, `list`, `code`, `delimiter`,
  `audio`, `quiz`, `person`. **First `[data-type="header"]` = H2, second = H3.**
- **Inline formatting** (on selection): `button.cdx-inline-toolbar__button[data-type=
  "bold"|"italic"|"link"]`; Ctrl+B / Ctrl+I toggles also work while typing.
- **Publish (DO NOT click)**: `button.button--type-primary` («Опубликовать»).

### Body approach — real-clipboard paste + restore passes
A **real** `Ctrl+V` from the OS clipboard is processed by Editor.js like a manual
paste (unlike a synthetic `ClipboardEvent`, which dropped paragraphs), so paragraphs,
H2/H3 headings and bullet/ordered lists survive a single paste. The adapter therefore
pastes the whole body once (HTML from `emit_body(doc, caption_marker=False,
quote_as_paragraph=True)`: quotes as `<p>`, images as `[[IMG:file]]` markers — put on
the real clipboard via an offscreen `contenteditable` + `execCommand('copy')`), then
restores what paste drops:
- **strong/em** — reapplied by selecting each run's char-offset range and pressing
  Ctrl+B/Ctrl+I (blocks addressed by Editor.js `data-id`).
- **quotes** — the editor CANNOT convert a paragraph to a quote, so the paragraph is
  emptied (Ctrl+A, Delete) and a native quote block is inserted in its place.
- **images** — VC strips `<img>`/data-URI on paste, so each `[[IMG:file]]` marker is
  replaced by a native upload (file chooser) with the caption typed into the image
  block's own caption field.

Mapping check: after paste, the adapter compares the `.ce-block` count to the IR block
count; on mismatch it logs a warning and skips the strong/em + quote passes (images
still run, matched by marker content).

### Image insertion (confirmed)
1. Ensure an empty active block (press Enter).
2. Open the toolbox ("+").
3. Intercept the native file chooser and JS-click the media item:
   ```python
   with page.expect_file_chooser() as fc:
       page.eval_on_selector('.ce-toolbox__item[data-type="media"]', "el => el.click()")
   fc.value.set_files("in/<slug>/images/imageN.png")
   ```
   (A plain `page.click` does NOT fire the chooser; the JS `el.click()` does.)
4. **Upload is async** — wait via `wait_for_function` until a NEW `<img>` exists AND
   has a real `http(s)` src (`complete && naturalWidth>0`). Skipping this scrambles
   block order in image-dense regions (the caret moves while the upload is in flight).
5. **Caption** = the image block's `.editor-tool-input--text-sm` contenteditable
   (use `.last`). Click + type. Press Enter afterwards to move to the next block.

### Lists & quotes
- **List** (`data-type="list"`): a SINGLE contenteditable `<ul class="editor-list-tool">`,
  one `<li>` per Enter (not one block per item). Ordered = same `<ul>` with modifier
  `editor-list-tool--ordered`; set it via the block gear
  (`.ce-block-action__settings-toggler`, JS-click) → tune `.ce-block-settings__item`
  whose text contains «Нумерованный», then re-focus the `<ul>`. Exit with a
  double-Enter on an empty last item.
- **Quote** (`data-type="quote"`): `<div class="editor-quote-tool">` with two fields —
  body `.editor-quote-tool .editor-tool-input--multiline` (wraps text in `<p>`) and
  author `.editor-quote-tool .editor-tool-input--text-sm` (leave empty; GDoc has no
  author). Enter in the body only inserts a newline; to exit, focus the author field
  and press Enter.
- The per-block gear is `.ce-block-action__settings-toggler` (inside `.ce-block__actions`),
  visible only on hover → trigger with a JS `el.click()`.

---

## Pikabu — Tiptap / ProseMirror (Vue-wrapped)

All VC block types are supported natively — **no degradation needed**. Headings have
two levels: `<h2>` → «Заголовок 1» (`node-heading-first-view__host`), `<h3>` →
«Заголовок 2» (`node-heading-second-view__host`).

### Navigation & auth
- New-post page: `https://pikabu.ru/add` (always a fresh post; never restores a draft).
- Auth persists in `.profiles/<client>/pikabu/` (`python cli.py login <client> pikabu`).
- A saved draft lives at `https://pikabu.ru/drafts`.

### Confirmed selectors
- **Title**: `textarea[placeholder="Заголовок"]`.
- **Body**: `.tiptap.ProseMirror` (contenteditable).
- **Formatting toolbar** by stable `data-test` (disabled until focus/selection):
  `editor-ctrl-heading`, `editor-ctrl-bold`, `editor-ctrl-italic`, `editor-ctrl-strike`,
  `editor-ctrl-link`, `editor-ctrl-quote`, `editor-ctrl-ul`, `editor-ctrl-ol`,
  `editor-ctrl-highlight` / `editor-ctrl-marker` / `editor-ctrl-spoiler`.
- **Publish (DO NOT click)**: `[data-test="story-publish"]`. **Save draft**: button
  «Сохранить черновик».

### Body — ONE high-fidelity paste
Dispatch a synthetic paste event carrying `text/html` onto `.tiptap.ProseMirror`:
```js
const dt = new DataTransfer();
dt.setData('text/html', html);
dt.setData('text/plain', html.replace(/<[^>]+>/g, ''));
el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles:true, cancelable:true}));
```
`<h2>/<h3>/<p>/<strong>/<em>/<ul>/<ol>/<li>/<blockquote>` all map to real Tiptap nodes
(h3 survives as the distinct second heading level). The adapter feeds
`emit_body(doc, caption_marker=False)` here.

### Image upload — paste a `File` (the "+→photo" button is a dead end)
Build a real `File` from the bytes in the page and paste it onto the editor:
```js
const res  = await fetch('data:' + mime + ';base64,' + b64);
const file = new File([await res.blob()], name, {type: mime});
const dt = new DataTransfer(); dt.items.add(file);
el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles:true, cancelable:true}));
```
Tiptap shows a `blob:` placeholder, uploads, then swaps in the final
`https://cs*.pikabu.ru/…` src — **wait for that http(s) src** (async). The floating
"+" → photo button fires no chooser/input/XHR — don't pursue it.

**Marker replacement:** the body is pasted with `[[IMG:file]]` marker paragraphs; for
each (matched BY FILENAME, top-to-bottom), select the marker `<p>`'s contents via a
DOM Range, paste the image File (replaces in place), then Backspace the leftover empty
paragraph.

### Caption — native field
Each image node has a sibling `div.node-image-caption-view__host` with an editable
`div[data-node-view-content]`. A DOM Range doesn't reliably sync to ProseMirror; instead
`scrollIntoView({block:'center'})` the caption host, compute its on-screen point, fire a
REAL `page.mouse.click(x,y)`, then `keyboard.type`. (Without the scroll, the click misses
in long articles and captions come out empty.)

### Draft save
Click «Сохранить черновик» → fires `POST …/save_draft_post` (200). The URL never changes;
wait on that response as the success signal. The adapter stops at a saved draft (never
publishes); empty tags/community are fine to SAVE (required only to PUBLISH).

---

## Onboarding a new platform (discovery pattern)

The discovery scripts were one-off, but the method is reusable:

1. **Seed an authenticated profile.** Launch a visible, persistent Chromium context
   (`launch_persistent_context("<.profile>", headless=False)`), log in by hand once;
   cookies persist for scripted runs.
2. **Identify the editor.** Find the new-post URL and the body container; determine the
   editor framework (Editor.js vs Tiptap/ProseMirror vs plain contenteditable) — it
   dictates everything else.
3. **Map controls.** Dump the toolbox / formatting toolbar (`{data-type|data-test, text}`
   in DOM order) to learn heading levels, lists, quote, image controls.
4. **Test body transport.** Try a high-fidelity HTML paste of a small sample covering
   every block + inline style; inspect the resulting node tags/classes. If paste is
   lossy (VC), fall back to per-block typing; if faithful (Pikabu), paste the whole body.
5. **Solve image upload.** Prefer the native file chooser; if that's a dead end, try
   pasting a real `File`. Always wait for the final CDN `https` src (uploads are async).
6. **Find the caption field and the save/draft flow.** Stop at a saved draft; never
   auto-publish.
7. Record the confirmed selectors + mechanisms here, then map the IR
   (`Heading/Paragraph/Image/ListBlock/Quote`) onto the platform's blocks in a new adapter.

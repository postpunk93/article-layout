> ## NON-NEGOTIABLE: this project NEVER publishes
>
> Every adapter stops at a built draft (plus the platform's own autosave where it
> exists) and leaves the browser window open. The final "publish"/"submit" action is
> ALWAYS performed by a human. Whatever we change in the pipeline, no publish button is
> ever clicked by this code. If this rule ever changes, the user will say so separately
> and explicitly.

# Platform notes (VC + Pikabu + Habr + Smartlab + Dzen + LiveJournal + WordPress)

> **Profiles are per-client now.** Each client has ONE shared Chrome profile at
> `.profiles/<client>/`, logged into every platform at once. `layout` opens that
> profile in a single window with one tab per requested platform. (Older builds used
> a separate `.profiles/<client>/<platform>/` profile per platform.)

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
- **Title is itself a `.ce-block`** inside `.codex-editor` (its editable carries
  `data-placeholder="Заголовок"`). Exclude it when counting/addressing body blocks:
  filter `.ce-block` to those WITHOUT a `[data-placeholder="Заголовок"]` editable.
- **Add-block "+"**: `.ce-toolbar__plus`. It is effectively 0-size, so Playwright
  treats it as NOT visible — `page.click` times out. ALWAYS JS-click it:
  `eval_on_selector('.ce-toolbar__plus','el=>el.click()')`. The caller must first put
  the caret in the target EMPTY block with a REAL click (anchors the toolbar + scrolls
  it into view).
- **Toolbox popover**: `.ce-popover.ce-toolbox.opened`; items are
  `li.ce-toolbox__item[data-type="…"]`. Order: `text`, `header` (H2), `header` (H3),
  `media` (image), `andropov` (link embed), `quote`, `list`, `code`, `delimiter`,
  `audio`, `quiz`, `person`. **First `[data-type="header"]` = H2, second = H3.**
  Wait for the opened popover with `state="attached"` (NOT visible): for a scrolled
  block it can render outside the viewport and a visible-wait times out.
- **Inline formatting** (on selection): `button.cdx-inline-toolbar__button[data-type=
  "bold"|"italic"|"link"]`; Ctrl+B / Ctrl+I toggles also work while typing.
- **Publish (DO NOT click)**: `button.button--type-primary` («Опубликовать»).

### Body approach — real-clipboard paste + restore passes
A **real** `Ctrl+V` from the OS clipboard is processed by Editor.js like a manual
paste (unlike a synthetic `ClipboardEvent`, which dropped paragraphs), so paragraphs,
H2/H3 headings and bullet/ordered lists survive a single paste. Validated end-to-end
on `in/lists-quotes` (72 body blocks, 1 quote, 10 images, 15 bold/italic runs).

Sequence that actually works (order is load-bearing):
1. Put the body HTML on the real clipboard via `navigator.clipboard.write` with a
   `text/html` Blob — our CLEAN html. (`grant_permissions(["clipboard-write"])` first.
   Do NOT use `execCommand('copy')` of a styled offscreen div: the browser bloats that
   to ~6× with inline styles and the editor under-segments it.)
2. Click the title and TYPE it. Typing leaves the caret at the title's true end.
3. `Enter` → moves the caret INTO the body and creates the first body block. The title
   is its own `.ce-block`, so a `Ctrl+V` while the caret is in the title pastes the
   whole article into the TITLE — you must move into the body first.
   > Do NOT press `End` before `Enter`. A long title wraps to multiple lines and `End`
   > goes to the end of the current visual LINE, so `Enter` splits the title mid-way
   > (first line stays in the title, the rest becomes the first body paragraph). Set
   > the clipboard BEFORE typing so no JS runs between the title and the paste.
4. `Ctrl+V` with NO JS in between (any JS that touches the selection drops the body
   caret and the paste no-ops).

HTML comes from `emit_body(doc, caption_marker=False, quote_as_paragraph=True,
img_sep=" ")`: quotes as `<p>`, images as `[[IMG file]]` markers.
> **Marker colon is fatal.** `[[IMG:file.png]]` ABORTS the multi-block paste — the
> editor reads `IMG:file.png` as a `scheme:path` link. A space (`[[IMG file]]`) pastes
> intact. (Brackets alone and `file.png` alone are both fine; it's the `word:word.ext`
> shape that triggers it.) Real article URLs could in principle trigger the same, but
> the mapping check below catches a short paste.

Then restore what paste drops:
- **strong/em** — reapplied by selecting each run's char-offset range and pressing
  Ctrl+B/Ctrl+I (body blocks addressed by Editor.js `data-id`).
- **quotes** — the editor CANNOT convert a paragraph to a quote, so the paragraph is
  emptied (Ctrl+A, Delete) and a native quote block is inserted in its place.
- **images** — VC strips `<img>`/data-URI on paste, so each `[[IMG file]]` marker is
  replaced by a native upload (file chooser) with the caption typed into the image
  block's own caption field.

Mapping check: after paste, the adapter compares the BODY `.ce-block` count (title
excluded) to the IR block count; on mismatch it logs a warning and skips the strong/em
+ quote passes (images still run, matched by marker content). Each quote/image is
best-effort so one failure can't abort the run.

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

## Habr — Tiptap / ProseMirror (custom, with auto image upload)

Habr's article editor is **Tiptap / ProseMirror** — same family as Pikabu, so the
body goes in as ONE high-fidelity HTML paste. Two things make Habr the easiest
target so far: it **auto-uploads images pasted as `<img>`** (no File-paste, no
markers), and the **title is the first node of the editor** (no separate field).

> **Login vs automation use DIFFERENT browsers (load-bearing).** Habr's login is
> behind **Yandex SmartCaptcha**, which detects the CDP/DevTools connection and
> renders a BLANK captcha in any Playwright-driven browser (bundled Chromium AND
> system Chrome alike — masking `navigator.webdriver` does NOT help). So:
> - **Login** must use a **hand-launched system Chrome** (no CDP) on the profile
>   dir → captcha renders → log in once; cookies persist in the profile.
> - **Automation** then uses **Playwright `channel="chrome"` with an ABSOLUTE
>   `user_data_dir`** on that same profile — it reuses the login (no captcha at
>   build time) and drives the editor normally.
> Bundled Chromium can NOT reuse the login (Chrome's app-bound cookie encryption is
> unreadable by the older bundled build); system Chrome reading its own profile is
> required. A RELATIVE `--user-data-dir` makes system Chrome fail to launch
> (`TargetClosedError`) — always pass an absolute path.

### Navigation & auth
- **Editor entry = the navbar pencil**, not a fixed URL: `a:has(svg.tm-header-user-menu__icon_write)`
  (svg class `tm-header-user-menu__icon_write`, title «Редактировать»). Clicking it
  routes to the right editor for the account (sandbox → `https://habr.com/ru/sandbox/new/`;
  a full account → its article editor). Prefer clicking the pencil over hardcoding.
- Logged-out marker: `.tm-header-user-menu__login` («Войти») is present.
- Auth persists in `.profiles/<client>/habr/` after the one-time hand-launched login.

### Confirmed selectors / structure
- **Body editor**: `.tiptap.ProseMirror` (one contenteditable holding the whole doc).
- **Title**: the FIRST node of the doc — `.tiptap .title` (an `<h1 class="title">`
  inside `div.title__wrapper[data-placeholder="Заголовок"]`). Click it and type the
  title; body paragraphs are the nodes after it (placeholder «Введите текст»).
- **Per-block context menu**: each block embeds a `.right-menu__container`; its items
  are `button.right-menu__item` («Параграф», **«Цитата»**, «Удалить»). The menu is
  `display:none` until hover, but a JS `.click()` on the «Цитата» button still fires
  the conversion. Match the target paragraph by its content text (strip the
  `.right-menu__container`/`.node__drag-control`/`.context-menu` text first).
- **Image caption**: each image block has a `figcaption.node_figcaption` holding an
  editable `<p data-placeholder="Подпись к изображению">`. A DOM range doesn't sync to
  ProseMirror — `scrollIntoView`, compute the figcaption's on-screen point, fire a REAL
  `page.mouse.click(x,y)`, then `keyboard.type` (the Pikabu caption lesson).
- **Settings button (stop point)**: a `button` with text **«Далее к настройкам»**
  (class `btn ... tm-button_color-horizon`), disabled until the body has content.
- **WYSIWYG/source toggle** exists (`button.switcher-control`, title «Выбор редактора») —
  we stay in WYSIWYG.
- The inline formatting toolbar is a Tiptap bubble menu (appears on selection), so it
  is not in the DOM at rest — paste carries the formatting, so it's rarely needed.

### Body — ONE high-fidelity paste (Pikabu-style synthetic event)
Dispatch a synthetic `paste` carrying `text/html` onto `.tiptap.ProseMirror` (same JS
as Pikabu). Verified on a sample: `<h2>` headings (rendered as a `node_heading` block),
`<strong>`/`<em>`, `<ul>` and `<ol>` all survive. **`<blockquote>` does NOT** — it
lands as a plain paragraph and must be converted afterward (per-block menu → «Цитата»).

### Images — paste `<img>`, Habr auto-uploads (no markers, no File-paste)
Unlike VC (strips images) and Pikabu (needs a real `File`), Habr **fetches and
re-hosts an image pasted as `<img src="data:…base64…">`**: after paste the `<img>`
src becomes `https://habrastorage.org/getpro/habr/upload_files/…`. So emit REAL
`<img>` with a base64 data-URI of each local file (no `[[IMG]]` markers) and **wait
for the habrastorage `https` src** before continuing (upload is async).

### Headings — single subheading level
Habr supports one subheading level (h1 = article title, h2 = subheading). Deeper
headings (h3+) are emitted as a bold line via `emit_body(..., max_heading_level=2)`.

### Stop point — advance to settings, never publish
After the body is built, click «Далее к настройкам» and STOP on the article-settings
screen (hubs / target audience / keywords are required there and left for the human).

### Validated end-to-end
`cli.py layout lists-quotes default habr` (72 IR blocks, 10 images, 1 quote, 2
captioned images): title set, body laid out 1:1 (9 headings, both lists, bold/italic),
all 10 images auto-uploaded to habrastorage, the quote converted to a native quote
block, both captions written into their figcaption fields, then stopped on the
settings screen. No marker/File-paste needed.

---

## Smartlab — Editor.js «redaktor 4» at `/topic/add2` (VC's engine, stock classes)

smart-lab.ru has **two** post editors. The legacy `/topic/add/` is TinyMCE 3.5.11
(iframe WYSIWYG; its images go through a clumsy per-image `lseditor/image.htm` dialog).
We target the **newer `/topic/add2`** instead — it is **Editor.js (Codex Editor)**,
the SAME engine as VC, and it **autosaves a draft** (the natural, publish-free stop).
Unlike the VC adapter (which pastes the body and restores lost formatting with
keyboard passes), add2 exposes the live Editor.js instance as **`window.editor`**, so
we build the body **deterministically via its JS API** (`clear()` + `render()`) — no
clipboard, no fragile restore passes, no block-count mapping. Only images can't go
through `render()` (they need an uploaded URL), so they keep VC's marker→native-upload
flow. Selectors are stock Editor.js (`cdx-*` / `ce-popover-item`), not VC's customized ones.

### Navigation & auth
- New-post editor: `https://smart-lab.ru/topic/add2` (holder `.codex-editor`).
- Auth is an **ordinary login/password** — STANDARD Playwright login flow (no captcha
  under CDP, unlike Habr): `python cli.py login <client> smartlab`.
- The editor mounts only for a logged-in user, so `.codex-editor` is the liveness marker.
- **add2 autosaves**: a background `POST https://smart-lab.ru/topic/autosave2/add/topic/`
  fires as you edit — this is the saved-draft signal (no save/publish button needed).

### Confirmed selectors / structure (stock Editor.js v2)
- **Live instance**: `window.editor` (has `clear()`, `render({blocks})`, `blocks`, `save()`).
- **Title = the FIRST `.ce-block`** — `render()`ing a `header` level-1 block makes it an
  `h1.ce-header` (placeholder «Заголовок»); body headings are level 2-6.
- **Toolbox** (used only for image insertion): open with `.ce-toolbar__plus` (JS-click;
  0-size until hover, as on VC); opened popover is `.ce-popover--opened`; items are
  `.ce-popover-item[data-item-name="…"]`. Confirmed names: `paragraph`, `header`,
  **`image`**, `list`, `checklist`, `quote`, `warning`, `code`, `delimiter`, `linkTool`,
  `table`.
- **Image caption**: `.image-tool__caption` (a `.cdx-input`, placeholder «Caption»).
- **Publish (NEVER click)**: an `<li>` with text «Опубликовать». No click is needed to
  save — autosave handles it.

### Body — `window.editor.clear()` then `render({blocks})` (JS API, not paste)
add2 AUTOSAVES and RESTORES a previous draft on load, so the editor is NOT empty. The
flow is:
1. `await window.editor.clear()` — drop the restored draft (leaves one empty block).
2. Build the blocks JSON from the IR and `await window.editor.render({blocks})`. Mapping:
   title → `{type:'header', data:{text, level:1}}`; `Heading` → `header` (level clamped to
   2-6); `Paragraph` → `paragraph`; `ListBlock` → `{type:'list', data:{style:'ordered'|
   'unordered', items:[…]}}` (flat string items); `Quote` → `{type:'quote', data:{text,
   caption:''}}` (NATIVE quote — no conversion); `Image` → a `paragraph` holding the
   `[[IMG file]]` marker (replaced by an upload below).
- **Inline bold/italic is rendered natively** by putting `<b>`/`<i>` inside `data.text`
  (use `<b>`/`<i>`, NOT `<strong>`/`<em>` — the Editor.js sanitizer drops those). No
  Ctrl+B/I restore pass, and no block-count mapping, is needed.

### Images — native upload via the toolbox (marker → file chooser → caption)
`render()` can't carry un-uploaded images, so the body holds `[[IMG file]]` markers.
For each marker: click into its paragraph, Ctrl+A/Delete to empty it, open the toolbox,
and `expect_file_chooser` around a JS-click of `.ce-popover-item[data-item-name="image"]`
(the image tool fires the OS file chooser directly). `set_files(path)` → smart-lab
uploads via `https://smart-lab.ru/include/ajax/uploadImg.php` and the `<img>` src becomes
`https://smart-lab.ru/uploads/…` — **wait for that http(s) src** (async). Then type the
caption into the new block's `.image-tool__caption`.

### Stop point — the autosaved draft, never «Опубликовать»
After body + images, the background autosave POST has the draft persisted. Wait for /
confirm a `…/topic/autosave2/add/topic/` request as the saved signal, then STOP. The
«Опубликовать» `<li>` is never clicked.

### Validated end-to-end
`in/lists-quotes` (72 IR blocks, 9 headings, 1 quote, both lists, 15 bold/italic runs,
10 images incl. 2 captioned): after `clear()`+`render()`, the editor held exactly 73
`.ce-block`s (title + 72) — 10 `ce-header`, 1 native `cdx-quote`, one unordered + one
ordered `cdx-list`, 11 `<b>` + 4 `<i>`; all 10 images uploaded to `…/uploads/…` with
zero leftover `[[IMG]]` markers, captions set on the two captioned images, and the
autosave POST observed. Nothing published.

---

## LiveJournal — Draft.js new post editor at `/post/` (like Dzen)

LJ's new post editor (`https://www.livejournal.com/post/`) is **Draft.js** — the same
engine as Dzen — so the body goes in as ONE real clipboard paste of clean HTML, and
only images need a native-upload pass. The adapter (`src/lj_adapter.py`) mirrors the
Dzen one.

### Navigation & auth
- New-post editor: `https://www.livejournal.com/post/` (body `.public-DraftEditor-content[contenteditable="true"]`).
- Auth is an **ordinary login** — STANDARD `open_context` (like VC/Smartlab), NO
  `manual_login`: the `default` profile drives fine under CDP. Add `manual_login` only
  if a login-time captcha ever appears.
- The Draft.js body mounts only for a logged-in user, so it doubles as the liveness marker.
- On load a **restore-draft modal** ("Открыть последний черновик?") must be dismissed —
  `text=Нет, спасибо` (fallback `[aria-label="Modal Window Close"]`).

### Confirmed selectors / structure
- **Title**: a plain `textarea.js--post-title` (placeholder «Придумайте заголовок»,
  maxlength 100) — `page.fill()` it (simpler than Dzen's contenteditable title).
- **Body**: `.public-DraftEditor-content[contenteditable="true"]`; blocks are
  `[data-block="true"]`.
- **Image inputs (PLupload)**: `input[type=file][accept*=".webp"]` — TWO share that
  accept list (a `multiple` one and a single one). They exist at editor load.
- **Image caption**: a native `textarea[class*="caption"]` (placeholder «Введите
  описание картинки») under each figure.
- **Publish (NEVER click)**: `button.js--toggle-submission-popup` («Настроить и опубликовать»).
- **Slash quick-insert** (`/` or `js--add-panel-trigger`) offers native blocks
  (Заголовок H2/H3, Цитата, Загрузить изображение, списки, …) — NOT needed by the adapter.

### Body — ONE real clipboard paste (clean HTML)
`emit_body(doc, caption_marker=False, quote_as_paragraph=False, img_sep=":")` then a
real `Ctrl+V` (set the system clipboard via `navigator.clipboard.write` with text/html;
`bring_to_front()` first — a real Ctrl+V only pastes into a FOCUSED tab). Verified: the
full 72-block body survives in one paste; `<blockquote>` → native `<blockquote
data-block="true">` quote block, `<ul>/<ol>` → native list-item blocks (no convert pass,
unlike VC). The user's earlier manual-paste hang was raw heavy GDoc content, not our
clean `emit_body` output.

### Images — single PLupload input uploads at the cursor (marker → upload → native caption)
The body holds `[[IMG:file]]` markers. For each (matched BY FILENAME, top-to-bottom):
1. Locate the marker block, **verify the caret actually landed in it** (re-click until
   `getSelection().anchorNode` is inside that block) BEFORE clearing — a blind
   Home/Shift+End/Delete during a focus race (the caret can still be in the PREVIOUS
   image's caption textarea) eats whichever block the caret is really in (observed: the
   preceding paragraph losing its opening words).
2. Clear the single-line marker (Home, Shift+End, Delete — NOT Ctrl+A, which selects the
   whole Draft.js editor).
3. `set_input_files` on the **single** (non-`multiple`) image input — PLupload inserts
   the figure at the cursor (the emptied marker block); no slash menu / file chooser.
4. **Wait for the real CDN src** (`ic.pics.livejournal.com`) before continuing (async),
   then tag the new figure with its source filename (`data-lj-file`). The marker clear
   leaves no stray blank block (no strip pass needed).

**Captions go in a SECOND pass, after EVERY image is uploaded** — NOT inline. Uploading
the next image RESETS the previous figure's caption `textarea` to empty (the figure
element survives, only its value is wiped; read-back right after setting it looks fine,
which is the trap). So once all uploads are done, fill each captioned figure's textarea
(found by its `data-lj-file` tag) — no further upload will wipe it.

### Stop point — the autosaved draft, never publish
This editor shows NO inline "saved" badge. The footer «Черновики» line gains
**«(сохранен в ЧЧ:ММ:СС)»** when autosave completes. Two gotchas:
- The URL gains `?draft=<draft-url>` right after the BODY paste — long before the images
  finish — so it is NOT a safe stop signal.
- The site renders that leading `с` as a **Latin `c`**, so match the ending
  `охранен в <time>`.
The adapter records the footer timestamp before the image edits and waits for it to
ADVANCE, so the LATEST content is known saved. `js--toggle-submission-popup` is never clicked.

### Validated end-to-end
`cli.py layout lists-quotes default lj` (72 IR blocks, 1 quote, both lists, 10 images
incl. 2 captioned): title set, body laid out (native quote + lists, bold/italic), all
10 images uploaded to `ic.pics.livejournal.com` with zero leftover `[[IMG]]` markers,
both captions set, preceding paragraphs intact, then stopped at the autosaved draft
(`.../post/?draft=…`). Nothing published.

---

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
`updateBlockAttributes(image,{caption})` + `removeBlock(markerParagraph)` (decode HTML
entities in the marker text first).

### Stop point — saved draft, never publish
`wp.data.dispatch('core/editor').savePost()`, then wait for `!isSavingPost()` and
`getCurrentPost().status === 'draft'`. "Опубликовать" is never clicked.

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

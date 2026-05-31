# Dzen adapter — design

Status: **DONE / validated end-to-end** — 2026-06-01, branch `feat/dzen-adapter`.

Fifth platform adapter on the shared `parser → IR → adapter` architecture
(after VC, Pikabu, Habr, Smartlab). Same shape: `build_document(page, doc,
images_dir, log)` + module constants, registered in `src/sessions.py:PLATFORMS`.

## Brainstorm decisions (locked)

| Aspect | Decision |
|---|---|
| Surface | **Article editor** (not the short "post"). Post editor noted as a possible future feature. |
| Editor entry | `https://dzen.ru/profile/editor/create` → "+" in navbar → "Написать статью" → article editor at `/profile/editor/id/<channel>/<doc>/edit`. |
| Login | **Manual** (Yandex SmartCaptcha blanks under CDP). |
| Stop point | **Autosaved draft** — build body + images, wait for autosave, stop. Cover/announce/publish stay manual. |
| Body strategy | **Clipboard paste + quote-restore pass.** Manual paste carries everything EXCEPT quotes; quotes need a per-block conversion via the inline toolbar Blockquote button. |

## Discovery findings (2026-05-31, live editor via CDP attach)

### Auth — UPDATE 2026-06-01: now uses the standard Habr-style flow
The CDP-attach mechanism below was correct at discovery time, but after a full production
login Yandex marks the device trusted and issues a **persistent** master SSO cookie, so the
session now survives a Chrome close and the standard `open_context` reaches the logged-in
editor (verified: `is_alive('default','dzen')` → True). Dzen was therefore converted to the
**same flow as Habr**: `manual_login` (non-CDP Chrome for the captcha) once, then
`open_context` for `is_alive`/`layout`. The CDP-attach code (`launch_debug_chrome`,
`cdp_endpoint`, the `cdp_attach` branch in cli.py) was removed. The discovery notes below are
kept as the historical record of why the live-attach approach was originally chosen.

### (historical) Auth — the Habr "login then reopen" scheme did NOT work for Dzen at discovery
- Manual login → close Chrome → reopen profile under Playwright **fails**: lands on
  `passport.yandex.ru/.../auth/add`. The master Yandex SSO cookie (`Session_id` on
  `.yandex.ru`/`passport.yandex.ru`) is **session-scoped and dropped on Chrome close**;
  only the persistent `.dzen.ru Session_id` survives, which is insufficient because
  `/profile/editor/create` force-redirects through `oauth.yandex.ru/authorize`.
- Confirmed not caused by the user's personal Chrome being open (tested with it fully closed).
- **Working approach: never close the browser.** Launch a real Chrome (no automation
  flags) with `--remote-debugging-port=9222`, user logs in, then Playwright
  `connect_over_cdp("http://localhost:9222")` attaches to the SAME live process.
  Session stays intact, anti-bot is satisfied (real Chrome, `navigator.webdriver`
  not set under connect_over_cdp). This is the adapter's run mechanism for Dzen —
  a departure from the other adapters' `open_context` (launch_persistent_context).

### Editor internals
- Editor is **Draft.js** (`public-DraftEditor-content`, custom `article-editor-desktop--*`
  React CSS modules). Content lives in DraftJS's immutable ContentState; direct DOM
  injection gets reconciled away → must go through paste + toolbar actions.
- **Two contenteditables**: title (first `.public-DraftEditor-content`, `spellcheck="false"`)
  and body (`div.public-DraftEditor-content[aria-describedby="placeholder-ZenDraftEditor"]`).

### Stable selectors (CSS-module hashes like `-XK` avoided; aria/data/stable ids used)
These are the selectors the adapter (`src/dzen_adapter.py`) actually uses — keep this table
in sync when fixing selector drift (Task 9).
| Purpose | Selector (constant) |
|---|---|
| Body | `.public-DraftEditor-content[spellcheck="true"]` (`BODY_SEL`) |
| Title | `.public-DraftEditor-content[spellcheck="false"]` (`TITLE_SEL`) |
| Studio "+" create button | `[data-testid="add-publication-button"]` (`ADD_PUBLICATION_SEL`, also `ALIVE_SEL`) |
| Body block (paste/marker scan) | `[data-editor="ZenDraftEditor"][data-block="true"]` |
| Image insert (side "+", reveal on gutter hover) | `[class*="side-button__sideButton"]` (`SIDE_BUTTON_SEL`) |
| Image upload (in popup) | click text `Загрузите файл` (`UPLOAD_BTN_TEXT`) inside `page.expect_file_chooser()` — the popup's `<input type=file>` is `display:none`, so a visibility-waiting `set_input_files` hangs |
| Uploaded image / figure | `figure.zen-editor-block-image` (img → CDN `avatars.dzeninfra.ru`) |
| Image caption | `textarea[class*="image-caption__input"]` (`CAPTION_SEL`) — a real `<textarea>`, NOT a `<figcaption>` (that exists only on the error placeholder) |
| Autosave status (stop marker) | `[class*="editor-header__status"]` (`STATUS_SEL`) → text is "Сохранено …"; match `/сохранен[оы]/i` (saved) which excludes "Сохранение…" (saving) |
| Plain paragraph block | class `zen-editor-block-paragraph` (headings are `<hN>`, lists `-ul`/`-ol`, quotes `-quote`) |
| Publish (do NOT click) | `[class*="editor-header__editBtn"]` |

### Live e2e VALIDATED (2026-06-01) — corrections found during the real run
1. **Body clear bug:** `Ctrl+A` in Draft.js selects the WHOLE editor, so clearing a marker block
   with `Ctrl+A`+`Delete` wiped the entire pasted body. Empty only the marker line via
   `Home`/`Shift+End`/`Delete`. Also `page.bring_to_front()` before the paste (over
   `connect_over_cdp` a real Ctrl+V only pastes into a FOCUSED tab).
2. **Image upload:** the popup `<input type=file>` is hidden → click "Загрузите файл" inside
   `expect_file_chooser` (see table).
3. **Caption:** a `<textarea>`, not `<figcaption>` (see table).
4. **Autosave status:** text is "Сохранено меньше минуты назад", not "Все изменения сохранены";
   matched with `/сохранен[оы]/i`.
5. **Blank line after each image:** the emptied marker leaves a blank paragraph after the figure.
   Strip it with click + `End` + forward-`Delete` (merges the NEXT block UP into the blank) —
   ONLY when that next block is a `zen-editor-block-paragraph`. A `Backspace` (merge UP) would
   delete the atomic image; merging a heading/list/quote would DEMOTE it. A blank before a heading
   is left in place (harmless).

Final acceptance (lists-quotes, 72 blocks): 9/9 headings kept, 10/10 images uploaded to CDN,
2/2 source captions set, quote + lists native, blanks stripped except 1 before a heading,
autosave detected, nothing published.

**Body selector note:** the `aria-describedby="placeholder-ZenDraftEditor"` attribute (seen on the
empty editor) is DROPPED once the body has content (the placeholder disappears), so the adapter
keys off the stable `spellcheck="true"` instead (title is `spellcheck="false"`).

**Quote conversion is NOT needed** (paste of a real `<blockquote>` yields a native quote block),
so the inline-toolbar `[aria-label="Blockquote"]` path is unused by the adapter — kept here only
as a fallback reference if a future Dzen change ever stops accepting pasted blockquotes.

### Create-article flow (verified)
`/profile/editor/create` (live session) redirects to the studio dashboard
`/profile/editor/id/<channel>`. From there: click `[data-testid="add-publication-button"]`
("+") → menu → "Написать статью" → lands in a fresh editor at
`/profile/editor/id/<channel>/<doc>/edit` with the body ready.

### Paste behaviour (verified — small representative snippet pasted live)
A single real Ctrl+V of clean HTML from `emit_body` carries, as NATIVE Dzen blocks:
- **Headings** `<h2>/<h3>` → real `<h2 class="zen-editor-block">` blocks ✅
- **Paragraphs** ✅
- **Bold/italic** → preserved as DraftJS inline styles (`font-weight:bold` / `font-style:italic`
  spans, not `<strong>/<em>`) ✅ — **no strong/em restore pass needed**
- **Quotes** → emit a semantic `<blockquote>` and Dzen makes a native
  `<blockquote class="zen-editor-block zen-editor-block-quote">` ✅ — **no quote-conversion
  pass needed.** (The user's "paste loses quotes" is a GDoc-clipboard artifact: GDoc emits
  styled paragraphs, not `<blockquote>`. Our clean HTML emits real `<blockquote>`.)
- **Lists** ul/ol → native `zen-editor-block-ul` with `<li class="zen-editor-block ...">` ✅
- **Images** → a pasted `<img>` makes an image block, but a **data-URI ERRORS**
  (`zen-editor-block-image__error`); Dzen does NOT ingest data-URIs (unlike Habr). So
  images must be uploaded natively (below). Each image block has a native `<figcaption>`.

**Conclusion:** Dzen body paste is the cleanest of all adapters — only IMAGES need a
post-paste pass. No strong/em, no quote conversion.

### Image upload (verified — uploaded to Dzen CDN)
- Side "+" button (revealed by focusing an empty block and hovering its left gutter):
  `button[class*="side-button__sideButton"]`, `data-tip="Добавить изображение"`.
- Clicking it opens an image popup containing a hidden
  `input[type=file]` (`class*="image-popup__file"`,
  `accept="image/png,image/jpeg,image/bmp,image/webp,image/gif"`).
- `set_input_files(<local path>)` on that input uploads to Dzen's CDN; the image block
  flips to `err:false` with `src` on `https://avatars.dzeninfra.ru/get-zen_doc/...`.
- Caption goes into the block's `<figcaption>`.
- Adapter plan: emit images as marker paragraphs `[[IMG:file]]` (VC-style), then per
  marker focus the block → reveal+click side "+" → `set_input_files` → wait for the
  `avatars.dzeninfra.ru` src → type caption into figcaption.

### Stop point / alive marker (verified)
Autosave indicator `span[class*="editor-header__status"]` reads "Все изменения сохранены".
Wait for that, then stop. Never click `[class*="editor-header__editBtn"]` (Опубликовать).

## Final adapter shape
- `src/dzen_adapter.py`: `EDITOR_URL`/studio nav, `ALIVE_SEL`, `build_document(page, doc, images_dir, log)`.
- Registered in `PLATFORMS` with a Dzen-specific note: **does not use `open_context`** —
  needs the live-Chrome + `connect_over_cdp` mechanism (see auth finding). `cli.py`/`sessions.py`
  will need a small branch for the CDP-attach run mode (design the integration in the plan).
- Body: `emit_body(doc, caption_marker=False, quote_as_paragraph=False, img_sep=":")`
  (real `<blockquote>`; images as `[[IMG:file]]` markers; captions set natively).
- Passes: (1) paste body; (2) per-image native upload + figcaption. That's it.

## All discovery questions: RESOLVED ✅

## Throwaway tooling
`discovery_dzen.py` — modes: `login`/`inspect` (manual-login+reopen — proven NOT to work,
bounces to passport), `serve` (launch live Chrome + debug port 9222), `attach`
(connect_over_cdp + dump), `pastetest` (create article + paste snippet + structural dump).
Delete after the adapter is built. NOTE: discovery created scratch drafts in the test
channel — delete them by hand.

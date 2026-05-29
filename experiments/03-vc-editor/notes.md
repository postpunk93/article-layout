# Experiment 03 — VC editor discovery (COMPLETE)

**Date:** 2026-05-29
**Result:** Full create-draft flow confirmed end-to-end (title + paragraphs +
uploaded image + caption + autosave). Screenshot `capture/step6_image_uploaded.png`.

## The editor is **Editor.js** (Codex Editor)
VC's post editor is an Editor.js instance. Body is a block model, not one
contenteditable. Block tools have classes like `editor-text-tool`,
`editor-header-tool`, `editor-tool-input`.

## Navigation & auth
- Open the editor directly: navigate to **`https://vc.ru/?modal=editor`** (opens
  the new-post modal; no need to click "Написать").
- Auth persists in the `.vc-profile` persistent context — scripted runs are
  already logged in after a one-time manual login.
- Page title when open: `🖊 Новый пост`.

## Confirmed selectors
- **Title** (Editor.js block 0): `div.editor-tool-input[data-placeholder="Заголовок"]`
  (contenteditable). Click + type.
- **Body root**: `.codex-editor`; blocks are `.ce-block`; a paragraph block's
  editable is `.editor-text-tool` (placeholder "Мы были где-то около Барстоу...").
- **Add-block "+"**: `.ce-toolbar__plus` — ONLY visible/clickable when the
  current block is EMPTY. (Create an empty block with Enter first.)
- **Toolbox popover** (after clicking +): `.ce-popover.ce-toolbox.opened`, items
  are `li.ce-toolbox__item[data-type="..."]`. Confirmed types in order:
  `text`, `header` (H2), `header` (H3), `media` (Фото/видео — IMAGE),
  `andropov` (link embed), `quote`, `list`, `code`, `delimiter`, `audio`,
  `quiz`, `person`.
  - First `[data-type="header"]` item = **H2**; second = H3.
- **Inline formatting toolbar** (on text selection): `button.cdx-inline-toolbar__button`
  with `data-type="bold"|"italic"|"link"`. (Ctrl+B / Ctrl+I likely also work —
  to confirm during adapter build.)
- **Publish button (DO NOT click)**: `button.button--type-primary` text "Опубликовать".

## Image insertion — CONFIRMED WORKING
1. Ensure an empty block is active (press Enter to create one).
2. Click `.ce-toolbar__plus` to open the toolbox.
3. Intercept the native file chooser and JS-click the media item:
   ```python
   with page.expect_file_chooser() as fc:
       page.eval_on_selector('.ce-toolbox__item[data-type="media"]', "el => el.click()")
   fc.value.set_files("in/<slug>/images/imageN.png")
   ```
   (A plain `page.click` on the media item did NOT fire the chooser; the JS
   `el.click()` does.)
4. The image uploads to VC and renders as a real image block.
5. **Caption field** appears as the image block's `editor-tool-input--text-sm`
   contenteditable (placeholder "Подпись"/"Описание"). Click + type the caption.

## Draft autosave — CONFIRMED
- As soon as body content is added, the URL gains `&action=edit&id=<NNN>` and a
  "Сохранено" indicator shows. The draft is saved automatically. Detect a saved
  draft by waiting for the URL to contain `id=`.

## Body text approach — DECISION: per-block typing (variant A), NOT paste
Tested clipboard `ClipboardItem(text/html)` + Ctrl+V (`capture/paste1_clipboard.json`):
- `<h2>` → header block ✓
- **`<strong>`/`<em>` were STRIPPED** (plain text) ✗
- **The `[[IMG:...]]` marker paragraph AND a following paragraph were DROPPED** ✗✗
Paste is lossy/unpredictable. So the adapter builds the body **block by block**:
- Title → type into the title block.
- Paragraph → type text; bold/italic runs via Ctrl+B / Ctrl+I toggles (to verify).
- Heading(2) → empty block → "+" → first `[data-type="header"]` item → type.
- Image → the confirmed image flow above → fill caption.
- New block between items via Enter.
- The `[[IMG:...]]`/`[[CAP:...]]` markers from emit_html are therefore NOT pasted;
  the adapter consumes the IR directly. (emit_html remains useful for debugging/
  future paste-capable platforms.)

## Verified during adapter build (all CONFIRMED working)
- **Ctrl+B / Ctrl+I inline toggles work** while typing runs → produce `<b>`/`<i>`
  in the block. The adapter toggles per run.
- **Caption** = the just-added image block's `.editor-tool-input--text-sm`
  (use `locator(...).last`). Typed caption attaches to the media block.
- **First `[data-type="header"]` item = H2** (placeholder "Подзаголовок"), renders
  as a section header. Used for our heading(level=2).
- After an image+caption, pressing **Enter** moves out of the caption and creates
  the next body block (so block flow continues cleanly).

## Full-article validation (2026-05-29)
Ran `vc_adapter.build_document` on the parsed `example/index.html`:
- 68 blocks built: title, 8 H2 headings, 10 images (image1..10), the rest
  paragraphs. image8 got its italic caption; others none — matches the parser.
- Draft auto-saved. Build took ~105s. No errors.

### BUG FOUND + FIXED: scrambled block order in image-dense regions
- Symptom: paragraphs out of order near clusters of images (image-sparse areas fine).
- Root cause: image upload is **async**; the adapter didn't wait for it. The old
  `wait_for_selector('.editor-tool-input--text-sm')` returned immediately for every
  image after the first (a caption field from a prior image already existed), so the
  code typed the next paragraphs while the upload was still in flight; Editor.js then
  inserted the image at the moved caret — several blocks too low — shifting paragraphs.
- Evidence: diffed the persisted draft's block order vs the parsed IR — scrambling was
  localised to image-dense rows, re-syncing in sparse regions.
- Fix (`_insert_image`): after `set_files`, wait via `wait_for_function` until a NEW
  `<img>` exists in the editor AND it has finished loading a real `http(s)` src
  (`complete && naturalWidth>0`). Also stopped pressing Enter after the final block
  (was leaving a trailing empty paragraph).
- Re-verified on the full article: **block order matches the IR exactly (diffs=0, 69
  blocks).**
Verdict: per-block adapter works end-to-end on the real article, order-correct.

## Lists & Quotes (discovered 2026-05-29, Task 6)

Probe scripts: `experiments/03-vc-editor/probe_*.py` (run from repo root). Live
findings captured in `experiments/03-vc-editor/capture/v*.{html,png}`.

### LIST tool (`data-type="list"`)
- A list is a SINGLE contenteditable element, NOT one Editor.js block per item:
  `<ul class="editor-list-tool" contenteditable="true"><li>item</li>…</ul>`.
- Items: type text, press **Enter** to start the next `<li>`. (Inline bold/italic
  via Ctrl+B / Ctrl+I as elsewhere.)
- **Ordered vs unordered**: the default insert is UNORDERED. Ordered uses the SAME
  `<ul>` element with an extra modifier class: `editor-list-tool--ordered`
  (renders "1. 2. 3."). Confirmed visually (`capture/v7_after.png`) and in DOM
  (`capture/v7_after.html`): `<ul class="editor-list-tool editor-list-tool--ordered">`.
- **To set ordered**: open the block's settings gear, then click the numbered tune:
  - Gear (per block, bypass hover with a JS click):
    `block.querySelector('.ce-block-action__settings-toggler').click()`
    where `block = ul.closest('.ce-block')`.
  - Tune popover items are `.ce-block-settings__item`. The list plugin shows two:
    **`Обычный`** (active = bulleted) and **`Нумерованный`** (numbered). Click the
    one whose innerText contains `Нумерованный`. The block re-renders to ordered;
    re-focus the `<ul>` before continuing (the tune popover stays open — close via
    Escape or by clicking back into the list).
- **Exit the list**: with the caret at the end of the last `<li>`, press **Enter**
  on an empty item (double-Enter) to drop out into a fresh paragraph block below.

### QUOTE tool (`data-type="quote"`)
- Block markup: `<div class="editor-quote-tool">` containing TWO contenteditable
  fields:
  - **Body** (where the quote text goes): the multiline field. SUPERSEDED during
    the adapter build — its size class flips between `--text-xl` (empty/short) and
    `--text-lg` (longer), so match on the stable `--multiline`:
    `.editor-quote-tool .editor-tool-input--multiline`. It wraps typed text in `<p>`.
  - **Author/source**: `.editor-quote-tool .editor-tool-input--text-sm`
    (placeholder "Источник"). LEAVE EMPTY — GDoc has no author concept.
    (NB: `--text-sm` is the same class used by an image caption; scope by
    `.editor-quote-tool` to disambiguate.)
- After inserting, focus the body field and type. The body is multiline, so Enter
  there only inserts a newline INSIDE the quote — it does NOT exit. SUPERSEDED:
  to leave the quote, focus the single-line author (`--text-sm`) field and press
  Enter (like an image caption); the author stays empty. (The earlier double-Enter
  hypothesis was wrong — it just stacks `<p>` newlines and absorbs the next block.)

### Block settings gear (general)
- The per-block gear is `.ce-block-action__settings-toggler` (inside
  `.ce-block__actions`), NOT `.ce-toolbar__settings-btn`. Only visible on hover, so
  trigger it with a JS `el.click()`.

### Toolbox "+" after a custom block — CAUTION
- `page.click('.ce-toolbar__plus')` sometimes reports the "+" as "not visible"
  right after inserting a custom (list/quote) block. A JS fallback works:
  `page.eval_on_selector('.ce-toolbar__plus', 'el => el.click()')`. The adapter's
  toolbox opener should try the normal click, then fall back to the JS click.

### Adapter implications (for Task 7)
- `_insert_list`: open toolbox → click `data-type="list"` → type items with Enter
  between them (no trailing Enter) → if ordered, gear → click `Нумерованный` tune →
  re-focus the list → double-Enter to exit. Since the method itself exits into the
  next empty block, the build loop must NOT add its own trailing Enter after a list.
- `_insert_quote`: open toolbox → click `data-type="quote"` → focus
  `.editor-tool-input--text-lg` → type body (author left empty) → double-Enter to
  exit. Same trailing-Enter caveat as lists.
- Verify the exact exit/`+` behavior during the live Task 8 run; prefer
  `wait_for_*` predicates over sleeps if anything proves async.

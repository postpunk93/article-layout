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

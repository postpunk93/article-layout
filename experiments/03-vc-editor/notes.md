# Experiment 03 — VC editor discovery

**Date:** 2026-05-29
**Goal:** record real selectors + the working paste mechanism before writing the adapter.

## Key discovery: the editor is **Editor.js** (Codex Editor)
VC's post editor is an Editor.js instance. DOM uses `codex-editor`, `ce-block`,
`ce-toolbar`, `cdx-inline-toolbar`, `editor-tool-input` classes. This shapes the
whole adapter: the body is a block model (paragraph/header/image blocks), not a
single contenteditable.

## New-entry navigation
- The editor opens as a MODAL on the same page at URL: `https://vc.ru/?modal=editor`
  (navigating directly to this URL is expected to open the editor — to confirm).
- Triggered from the feed by the button `button.button--type-secondary` with text "Написать".
- Login: persisted in the `.vc-profile` persistent context (logged in by hand once).
  Subsequent scripted runs are already authenticated.
- Page title when editor open: `🖊 Новый пост`.

## Selectors (confirmed from capture/candidates.json)
- **Title field**: `div.editor-tool-input[data-placeholder="Заголовок"]`, `contenteditable="true"`
  (classes: `editor-tool-input editor-tool-input--multiline editor-tool-input--text-lg editor-tool-input--with-limit`).
- **Body editor root**: `.codex-editor` ; blocks are `.ce-block` / `.ce-block__content`.
- **Add-block ("+") button**: `.ce-toolbar__plus`.
- **Inline formatting toolbar** (appears on text selection): `button.cdx-inline-toolbar__button`
  with `data-type="bold"`, `data-type="italic"`, `data-type="link"`.
- **Inline link input**: `input.cdx-inline-toolbar__input` (placeholder "Вставьте ссылку ...").
- **Block toolbox search**: `input.ce-toolbox-search-input` (placeholder "Поиск").
- **Publish button**: `button.button--type-primary` with text "Опубликовать".

## Still TODO (next discovery round — Claude-driven, login persisted)
- Body paragraph editable selector (only the title contenteditable exists in the
  empty editor; body block editable appears after focusing the body).
- Image insertion flow: click `.ce-toolbar__plus` -> toolbox -> the "image" tool
  item -> the `input[type=file]` that receives the upload (none present in empty editor).
- Caption field on an inserted image block.
- How a saved draft is detected (autosave indicator / draft list).

## Text paste mechanism — to test
- [ ] clipboard write via context.grant_permissions(["clipboard-write"]) + Ctrl+V
- [ ] dispatch a `paste` event with DataTransfer(text/html)
- Editor.js converts pasted HTML to blocks (h2->header, p->paragraph, strong/em inline).
  Must verify whether our emit_body() HTML maps cleanly and whether `[[IMG:...]]` /
  `[[CAP:...]]` markers survive as plain paragraph text.

## Markers / fallback
- If markers don't survive or cursor placement is unreliable -> fall back to
  per-block typing using the "+" toolbox and the title/body editables. Decision: <pending discovery>

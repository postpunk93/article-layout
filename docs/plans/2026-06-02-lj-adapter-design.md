# LiveJournal adapter — design

**Date:** 2026-06-02
**Status:** approved (brainstorm), ready for implementation plan

## Goal

Add a `lj` platform that lays out a parsed GDoc article as an **autosaved draft** in
LiveJournal's new post editor (`https://www.livejournal.com/post/`), reusing the
shared per-client profile and the existing all-or-nothing `login/status/layout` CLI.
Never publish — stop at the autosaved draft, like every other adapter.

## Recon findings (verified live, not assumed)

Driven against a logged-in `default` profile via `recon_lj.py` + `probe_lj_paste.py`:

- **Body editor is Draft.js** — `div.public-DraftEditor-content[contenteditable="true"]`,
  `role=textbox`. Same engine as Dzen, so the proven Draft.js handling (block
  manipulation, `Home`/`Shift+End` line-select, the `Ctrl+A`-selects-everything
  caveat, marker→image replacement) transfers directly.
- **Title** is a plain `textarea.js--post-title` (maxlength 100, placeholder
  "Придумайте заголовок") — set with `fill()`, simpler than Dzen's contenteditable title.
- **Single clean-HTML paste SURVIVES.** `probe_lj_paste.py` pasted the full 72-block
  body (15 KB HTML) in one `Ctrl+V`: 77 Draft.js blocks, 14 169 chars, stable after
  6.5 s, no revert. Small chunks and a single paragraph also survived. The user's
  earlier manual-paste hang was the **raw heavy GDoc content**, not paste per se — our
  `emit_body` output is clean and the editor accepts it. → **paste architecture (like
  Dzen) is viable; no block-by-block build needed.**
- **Slash quick-insert menu** (`js--quickInsertPanel`, opened by `/` or the
  `js--add-panel-trigger` "+") offers native blocks: Заголовок H2/H3, **Цитата**,
  Хайлайт, **Загрузить изображение**, маркированный/нумерованный список, разделитель,
  опрос, коллаж, видео, кат. **No raw-HTML/source mode** in the new editor.
- **Image upload is native**: hidden `input[type=file]` with
  `accept=".jpg,.jpeg,.png,.webp,.gif,.heic"` (PLupload; one `multiple`, one single).
  Same `set_input_files` pattern as Smartlab/Habr.
- **Draft autosave + restore modal**: on load a `js--restore-draft-modal`
  ("Открыть последний черновик?") must be dismissed (`text=Нет, спасибо`). Drafts
  autosave ("Управление черновиками"). Publish button is `js--toggle-submission-popup`
  ("Настроить и опубликовать") — never click it.
- **Login**: the `default` profile, logged in once via the standard `manual_login`
  Chrome, drives fine under CDP (`open_context`, `channel=chrome`) — the paste probe
  ran through it. Treat LJ like VC/Smartlab (standard `open_context`); add
  `manual_login` only if a captcha appears at login time.

## Architecture

Mirror `src/dzen_adapter.py`. New module `src/lj_adapter.py` exposing
`build_document(page, doc, images_dir, log=print)`:

1. **Open editor** — `page.goto(POST_URL)`, wait for `BODY_SEL`
   (`.public-DraftEditor-content[contenteditable="true"]`), dismiss the
   restore-draft modal (`text=Нет, спасибо`, fallback `[aria-label="Modal Window Close"]`).
2. **Title** — `page.fill(TITLE_SEL, doc.title)` where `TITLE_SEL = "textarea.js--post-title"`.
3. **Body** — `emit_body(doc, quote_as_paragraph=False, img_sep=":", caption_marker=?)`;
   `bring_to_front()`, set clipboard (html+plain), click body, `Ctrl+V`.
4. **Images** — for each `Image` block, replace its `[[IMG:file]]` marker with a
   natively uploaded image via the hidden file input (Dzen-style marker locate →
   focus → upload), then set caption.
5. **Stop at draft** — wait for the autosave "saved" indicator; never click
   `js--toggle-submission-popup`.

### Registry (`src/sessions.py` `PLATFORMS`)

```
"lj": {
  "build_document": lj_adapter.build_document,
  "editor_url": lj_adapter.POST_URL,
  "alive_marker": lj_adapter.ALIVE_SEL,   # = BODY_SEL, mounts only when logged in
}
```

No `manual_login` unless login-time captcha forces it.

## Open implementation-time recon (TDD probes, NOT architecture forks)

Resolve each with a quick live probe during implementation:

- **(a) Quote rendering** — does pasted `<blockquote>` become a native «Цитата»
  block? Dzen does; verify for LJ. If not, fall back to a post-paste convert pass.
- **(b) Image insert mechanism + caption** — exact gesture to land an upload at the
  marker block, and whether the image block has a **native caption field**. If yes,
  `caption_marker=False` + set caption natively (like Pikabu/Dzen); if no,
  `caption_marker=True` and leave the caption as a following paragraph.
- **(c) Autosave indicator** — the selector/text that signals the draft is saved, for
  the stop condition (Dzen waits for `/сохранен[оы]/i`).

## Out of scope (YAGNI)

- LJ-specific blocks with no IR source: cut, polls, collages, highlight, video.
- Publish / submission popup configuration.
- Tags, communities, post settings.

## Testing

- Unit: pure helpers (e.g. `body_html`) tested like `test_dzen_adapter.py` — no browser.
- E2E: run `cli.py layout` for a client against the `lj` platform on a real sample
  (`in/lists-quotes`, `in/chernika`), confirm a draft with title, structured body and
  uploaded images; verify it stops at autosave and never publishes.

## Cleanup

Delete scratch files before the feature commit: `recon_lj.py`, `probe_lj_paste.py`,
`recon_lj_dump.json`, `recon_summary.txt`.

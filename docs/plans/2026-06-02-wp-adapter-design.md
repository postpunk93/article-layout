# WordPress / Gutenberg adapter (ruminlab.ru) — design

**Date:** 2026-06-02
**Status:** implemented; e2e-validated on in/synthetic
**Branch:** `feat/wp-adapter`

## Goal

Lay out a parsed GDoc `Document` as a **draft** post in our own WordPress site
(ruminlab.ru), Gutenberg block editor. One fixed site — just another platform in
the unified one-window/one-profile flow. Never publishes: stops at a saved draft.

## Recon findings (validated live, see `recon_wp.py`)

A real `Ctrl+V` of our clean body HTML (the same clipboard mechanism the VC/LJ
paste adapters use) produced **native Gutenberg blocks** with no per-block
toolbox work:

- `core/heading` with correct `level` (H2/H3)
- `core/list` (ul/ol) with `core/list-item` inner blocks
- `core/quote` directly from `<blockquote>` (no "empty paragraph + insert quote"
  dance like VC needed)
- **bold + italic preserved inline** (confirmed on screenshot)
- **images survive paste**: `<img>` emitted as a data-URI is **auto-sideloaded
  into the media library** — the resulting `core/image` has a real `http` `url`
  and an attachment `id`. No file-chooser upload loop needed (like Habr's
  data-URI auto-upload path).

Other facts that shape the design:

- The editor **canvas is in an iframe** (`iframe[name="editor-canvas"]`), but the
  `wp.data` store lives on the **top window** — so title, captions, and save are
  done programmatically via `wp.data`, never touching the iframe.
- **Captions do not auto-attach**: our `[[CAP:…]]` markers land as separate
  paragraphs after each image; they need a cleanup pass.
- **Title must be set separately** (pasting into the title field swallows the
  first body block) — set via `wp.data.dispatch('core/editor').editPost({title})`.
- **Save draft**: the "Сохранить черновик" button exists (match by text/aria; the
  classic `.editor-post-save-draft` class is absent in this WP). `wp.data`
  `savePost()` is the primary path. "Опубликовать" is never touched.
- **Liveness marker**: `.editor-document-tools__inserter-toggle` — a top-window
  element present only when the editor loads (i.e. logged in).

## Chosen approach: A — paste + `wp.data` cleanup

Rejected alternatives:
- **B** (emit `<figure><figcaption>` so paste fills the native caption, dropping
  the cleanup pass) — kept as a quick try during implementation; fall back to A's
  cleanup if figcaption is dropped on paste.
- **C** (fully programmatic `wp.blocks.createBlock` + `insertBlocks`, REST media
  upload) — reimplements what paste already does perfectly; not worth it.

## Module & registration

- New `src/wp_adapter.py` (generic Gutenberg engine; one site for now).
- Constants: `SITE = "https://ruminlab.ru"`,
  `EDITOR_URL = f"{SITE}/wp-admin/post-new.php"`,
  `ALIVE_SEL = ".editor-document-tools__inserter-toggle"`.
- Register in `sessions.PLATFORMS` under key `"ruminlab"`:
  `build_document`, `editor_url=EDITOR_URL`, `alive_marker=ALIVE_SEL`.
  Standard login (plain user/password, no captcha) → `open_context` under CDP
  like VC/LJ; no `manual_login` flag.

## `build_document(page, doc, images_dir, log)` flow

All steps drive the top-window `wp.data` store; the iframe is touched only for the
single body paste.

1. `grant_permissions(["clipboard-read","clipboard-write"])`; `goto(EDITOR_URL)`;
   poll until `wp.data.select('core/block-editor')` is up (editor ready).
2. **Title:** `wp.data.dispatch('core/editor').editPost({title: doc.title})`.
3. **Body in one paste:**
   `emit_body(doc, quote_as_paragraph=False, caption_marker=True, img_sep=" ",
   image_src=<data-URI from images_dir>)` → put on the real clipboard → click the
   first body block inside `frame_locator('iframe[name="editor-canvas"]')` (the
   default empty paragraph) → `Ctrl+V`. Headings/lists/quote/bold/italic arrive
   natively; data-URI `<img>` is sideloaded by WP.
4. **Wait for image sideload:** poll `getBlocks()` until every `core/image` `url`
   is `http(s)` (not `data:`/`blob:`), i.e. the attachment exists. ~60s timeout.
5. **Captions (one `evaluate` cleanup pass):** walk top-level blocks; for each
   `core/image` immediately followed by a paragraph whose text matches
   `^\[\[CAP:(.*)\]\]$`, `updateBlockAttributes(image, {caption})` and
   `removeBlock(markerParagraph)`. (Try B's `<figure><figcaption>` first; if the
   native caption sticks on paste, this pass is dropped.)
6. **Save draft:** `dispatch('core/editor').savePost()`; wait for
   `isSavingPost()===false` and `getCurrentPost().status==='draft'`; fallback —
   click "Сохранить черновик" by text. **Never publishes.**

## Error handling

Same posture as the other adapters:
- Captions are best-effort per image (`try` around each) — one failure does not
  abort the rest.
- If the `core/image` count does not match the IR image count, log a warning and
  leave blocks as-is.
- Editor-not-ready raises — but the all-or-nothing liveness gate catches a dead
  session before `build_document` runs.

## Stop signal

A saved draft (status `draft`). The window stays open for the human to review and
publish manually (shared `wait_until_all_closed`). Publish is always a human step.

## Testing

Per project rule, e2e on `in/synthetic` (not long real articles):
- **e2e:** `python cli.py layout synthetic <client> ruminlab` → draft with correct
  blocks, media-library images, and captions; assert status `draft`, not published.
- **unit (light):** `"ruminlab"` is registered in `PLATFORMS`; `emit_body(...,
  image_src=...)` emits an `<img>` plus the caption marker (latter already covered
  by `emit_html` tests). The caption-cleanup JS is covered by the e2e run.

## Cleanup

Remove (or gitignore) `recon_wp.py` and the `_recon` profile after merge.

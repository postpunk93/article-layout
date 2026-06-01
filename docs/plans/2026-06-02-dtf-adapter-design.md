# DTF adapter — design

**Date:** 2026-06-02
**Status:** implemented, validated e2e (DTF + VC regression)

## Goal

Add a `dtf` platform that lays out a parsed GDoc article as an **autosaved draft** in
DTF's editor, reusing the shared per-client profile and the existing all-or-nothing
`login/status/layout` CLI. Never publish — stop at the autosaved draft, like every
other adapter.

DTF (dtf.ru) and VC (vc.ru) both run Komitet's **Osnova** engine (Editor.js), so the
editor is expected to be ~identical to VC. The adapter therefore reuses VC's proven
approach wholesale: one real clipboard paste for the body, then restore passes for
strong/em, quotes, and images.

## Recon findings (verified live, not assumed)

Driven against the logged-in `default` profile via `recon_dtf.py` (scratch):

- **Editor URL** confirmed: `https://dtf.ru/?modal=editor` (the `default` profile needed
  a one-time DTF login — VC's session does NOT carry to dtf.ru; separate domain).
- **Selectors identical to VC.** On the empty editor: `div.editor-tool-input[data-placeholder="Заголовок"]`,
  `.codex-editor`, `.ce-block`, `.ce-toolbar__plus` each present. `CAPTION_SEL`
  (`.editor-tool-input--text-sm`) and `QUOTE_BODY_SEL`
  (`.editor-quote-tool .editor-tool-input--multiline`) are absent only because no image/
  quote block exists yet — same as VC; they appear when those blocks are created. → No
  selector divergence; `dtf_adapter` reuses VC's constants verbatim.
- **Save status** confirmed: the footer cycles **«Сохранение» → «Сохранено»** after an
  edit (matches the screenshot's «Сохранено ✓»). This is the correct stop signal.
- **Premature `id=` confirmed:** typing just the title produced
  `…&action=edit&id=5096504` in the URL immediately — before any images. So `id=` is NOT
  a valid "saved" signal; wait for «Сохранено» instead.
- **Login:** standard `open_context` (channel=chrome) drives DTF fine once logged in —
  no `manual_login` needed (no captcha at the editor).

## Approach decision

Considered three ways to share VC's logic:

- **A — thin delegation** (`dtf_adapter` calls `vc_adapter.build_document` with a URL
  override).
- **B — copy the file** (`vc_adapter.py` → `dtf_adapter.py`, change the URL).
- **C — extract a shared `osnova` core** with vc/dtf as thin configs.

**Chosen: B (copy).** It matches the established project convention — every platform
(pikabu/habr/smartlab/dzen/lj) is a self-contained adapter file, independently
tweakable when a platform drifts. It also leaves the already-merged, validated VC
adapter untouched (zero regression risk) except for one shared bug fix below. The
duplication cost is accepted as the price of the one-file-per-platform model.

## Architecture

Copy `src/vc_adapter.py` → `src/dtf_adapter.py` verbatim. The whole pipeline carries
over unchanged: clipboard paste of the body, then the restore passes
(strong/em by char-range, paragraph→native-quote, `[[IMG file]]` marker→native upload
+ caption), block addressing via Editor.js `data-id`, visible browser, stop at draft.

Only platform-specific constants change:

- `EDITOR_URL` → DTF's editor (expected `https://dtf.ru/?modal=editor`; confirm in recon).
- `TITLE_SEL`, `CAPTION_SEL`, `QUOTE_BODY_SEL`, and the `.codex-editor` / `.ce-block` /
  `.ce-toolbar__plus` / `.ce-toolbox__item[data-type=...]` selectors — expected
  identical (same Osnova engine). Any that recon shows differ are edited only in
  `dtf_adapter.py`; VC is not touched.

### Registry (`src/sessions.py` `PLATFORMS`)

```
"dtf": {
  "build_document": dtf_adapter.build_document,
  "editor_url": dtf_adapter.EDITOR_URL,
  "alive_marker": dtf_adapter.TITLE_SEL,   # title field renders only when logged in
}
```

Standard `open_context` login (like VC/Smartlab/LJ) — no `manual_login` (DTF has no
CDP-incompatible captcha at login).

## Stop-signal fix (applies to VC *and* DTF)

The current VC adapter waits for `id=` to appear in `location` as its "draft saved"
signal. **This is wrong:** on both VC and DTF the `id` appears in the URL immediately
after the *first* edit (the first paste) — long before images finish uploading. So the
adapter currently declares success prematurely.

The editor shows a footer save status next to the «Опубликовать» button:
«Сохранение» (saving) → «Сохранено ✓» (saved). The correct stop signal is to wait for
a stable **«Сохранено»** *after* the last mutating action (the final image upload), so
the captured save includes all images.

- Selector for the footer status confirmed in recon; match the footer text
  «Сохранено» / «Сохранение».
- To avoid catching an early «Сохранено» from the first paste, wait after the last
  upload for the autosave cycle to settle on «Сохранено» (not «Сохранение»).
- Never click «Опубликовать».

This is fixed in **both** `vc_adapter.py` (the original bug) and the new
`dtf_adapter.py`, so VC needs a quick e2e re-validation that it still reaches autosave.

## Synthetic test document

Goal: a short, all-cases fixture that does not expose real articles in drafts and
speeds up testing.

- **Format:** a real `.docx` authored to our GDoc conventions (the user reviews it in
  Google Docs, then "Download → HTML" to feed the pipeline — the pipeline consumes the
  GDoc HTML export, not the `.docx` directly).
- **Generator:** `tools/make_test_doc.py` (python-docx, reproducible, version-controlled)
  → `fixtures/synthetic.docx` + two tiny embedded PNGs.
- **Conventions baked in:** `Heading 1` = title; `Heading 2`/`Heading 3` = headings;
  yellow text highlight = quote; *italic* text under an image = caption; **bold**/*italic*
  inline runs; bulleted + numbered lists.
- **Content (~1 screen):** H1 title → paragraph with bold+italic → H2 → paragraph → H3
  → bulleted list (one item with bold/italic) → numbered list → yellow quote →
  image #1 + italic caption → image #2 + italic caption → short closing paragraph.
  Two images exercise multi-image marker matching and per-image captions.

**Caveat (round-trip risk):** how Google Docs re-exports the `.docx` to HTML — notably
the caption's placement relative to `<img>` within one `<p>` — is only known after the
manual Google round. If the export diverges from what the parser expects, fix either
the `.docx` (generator) or the parser as a separate step. The `.docx` is therefore
prepared **before** the DTF e2e: the user runs the Google round, drops the resulting
`in/synthetic/` folder, and DTF is validated on that.

## Error handling (inherited from VC, unchanged)

- Block-count mismatch → WARNING, skip strong/em + quote passes (fix by hand), still
  upload images.
- Per-quote and per-image steps are best-effort: one failure does not abort the rest
  (the marker/paragraph is left in place).
- Image missing on disk → WARNING, leave the `[[IMG file]]` marker in the body.

## Out of scope (YAGNI)

- DTF-specific blocks with no IR source.
- Publish / any submission flow.
- Tags, subsites, post settings.

## Testing

- Unit: `dtf_adapter.format_segments` (and any pure helper) covered like
  `test_vc_format_segments.py` — no browser.
- E2E: run `cli.py layout` for the `default` client against `dtf` on the synthetic
  `in/synthetic/` sample; confirm a draft with title, structured body (H2/H3, lists,
  bold/italic, native quote) and two uploaded images with captions; verify it stops at
  the «Сохранено» autosave and never publishes.
- Regression: re-run the VC e2e after the stop-signal fix to confirm VC still reaches
  autosave.

## Implementation-time recon (quick live probes, NOT architecture forks)

1. Open DTF editor in the `default` profile; confirm `TITLE_SEL` appears (session alive
   + selector confirmed) and the exact `EDITOR_URL`.
2. Diff VC's key selectors against the live DTF DOM: `.codex-editor`,
   `.ce-block[data-id]`, `.ce-toolbar__plus`, `.ce-toolbox__item[data-type="quote"|"media"]`,
   `CAPTION_SEL`, `QUOTE_BODY_SEL`. Record any divergence.
3. Confirm the footer save-status selector/text («Сохранено» / «Сохранение») for the
   stop condition.

## Cleanup

Delete any scratch recon files before the feature commit.

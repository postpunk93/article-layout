# 05 — Two-level heading controls (VC + Pikabu)

Discovery for the two-level subheadings work (see
`docs/plans/2026-05-29-heading-levels.md`). The old single-level assumption from
experiment 04 was wrong; both platforms expose two subheading levels.

Probes (run by hand against authenticated profiles). NOTE: run by direct path,
not `-m` (the package name starts with a digit / has a hyphen):

- `python experiments/05-heading-levels/probe_vc_headings.py`  → `vc_toolbox.json`
- `python experiments/05-heading-levels/probe_pikabu_h3.py`     → `pikabu_after_paste.json`

## VC — selector/index for H3

Decides which toolbox item `vc_adapter._insert_heading` clicks per level.

**Confirmed.** The `.ce-toolbox__item[data-type="header"]` items appear in DOM
order:

- index `[0]` = «Подзаголовок H2»  → source H2 (level 2)
- index `[1]` = «Подзаголовок H3»  → source H3 (level 3)

So: `idx = 0 if level <= 2 else 1`. (Full toolbox dump in `vc_toolbox.json`.)

**Task 3 verified end-to-end** (`verify_vc_levels.py` → `vc_levels_after_build.json`):
building the minimal H1/H2/H3 doc, the source H2 renders as a block with class
`editor-header-tool--h2` and the source H3 as `editor-header-tool--h3`. VC heading
blocks are NOT semantic `<h2>/<h3>` tags — the level lives in the `--hN` class.

## Pikabu — does `<h3>` survive paste?

Decides whether Task 4 needs a per-node fallback.

**Confirmed: yes, no fallback needed.** Pasting
`<h2>Level two</h2><h3>Level three</h3>` via the adapter's synthetic-paste path
yields `count = {h1: 0, h2: 1, h3: 1}` — both levels land as distinct nodes:

- `<h2>` → `node-heading-first-view__host…` («Заголовок 1»)
- `<h3>` → `node-heading-second-view__host…` («Заголовок 2»)

`emit_html` already emits `<h{level}>`, so Pikabu needs no adapter change beyond a
regression test that `emit_body` emits `<h3>` for a level-3 heading.

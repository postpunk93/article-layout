# 05 — Two-level heading controls (VC + Pikabu)

Run the two probes (authenticated browser required), then fill in the answers below.

- `python -m experiments.05-heading-levels.probe_vc_headings`  → `vc_toolbox.json`
- `python -m experiments.05-heading-levels.probe_pikabu_h3`     → `pikabu_after_paste.json`

## VC — selector/index for H3

<!-- Which `.ce-toolbox__item` to click for «Подзаголовок H3»: the data-type and
the index among `data-type="header"` items (expected [0]=H2, [1]=H3). This tells
Task 4 exactly which toolbox item `_insert_heading` must click for a level-3 heading. -->

## Pikabu — does `<h3>` survive paste?

<!-- Whether the pasted `<h3>` stays a distinct second heading level («Заголовок 2»)
or is collapsed to `<h2>` / dropped. This decides whether Task 4 needs a per-node
fallback (e.g. emit H3 as bold/another construct) when building the Pikabu body. -->

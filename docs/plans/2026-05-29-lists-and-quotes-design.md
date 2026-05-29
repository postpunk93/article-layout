# Design: List and Blockquote support (GDoc → IR → VC)

Date: 2026-05-29
Status: Approved (brainstorm), pending implementation plan
Scope: extend the existing parser / IR / VC adapter to carry two new GDoc
conventions through to the VC (Editor.js) editor: **lists** and **yellow-highlight
blockquotes**.

## Context

The VC pipeline is built and validated end-to-end: `run_vc.py in/<slug>` parses a
GDoc "Web page (.html)" export into a platform-agnostic IR (`src/parser.py`,
`src/ir.py`) and drives the VC Editor.js editor block-by-block (`src/vc_adapter.py`)
to a saved draft. Currently the IR carries Heading, Paragraph, and Image (with
italic-keyed captions). Lists and quotes are dropped.

A real sample article (`example/lists-quotes/`, the user's `Copyof.html`) was added
that contains both conventions, so detection can be designed against real markup.

### Observed real markup (from the sample)

- **Lists are real tags**, direct children of `<body>`:
  - `<ol class="c11 lst-kix_… start" start="1"><li class="c2 li-bullet-0"><span class="c1">…</span></li>…</ol>`
  - `<ul class="c11 lst-kix_… start"><li …><span class="c1">…</span></li>…</ul>`
  - The earlier memory note claiming GDoc flattens lists to `<p>` was wrong — that
    article simply had no lists.
- **Yellow highlight** is a CSS class applied to a paragraph's spans:
  - `.c10{background-color:#ffff00}`; used as `<p class="c3"><span class="c1 c10">…</span></p>`.
  - The blue `#c9daf8` (`.c13`) is an **orphan style definition** — defined in the
    export CSS but applied to no visible text. Not mapped.

## Decision: Approach A (chosen)

Sequence the work by risk. The parser + IR layer is deterministic and fully
testable offline against the real sample; land it first via TDD. The VC adapter
interaction for the `list` / `quote` toolbox tools is genuinely unverified — do a
short live **discovery** pass (recorded in `experiments/03-vc-editor/notes.md`)
before writing the adapter methods. This mirrors the discovery → adapter rhythm that
already worked for the image flow.

Rejected: B (full vertical slice — mixes deterministic and flaky live work);
C (emit lists/quotes as plain paragraphs — loses the semantic blocks).

## Data model (IR — `src/ir.py`)

```python
@dataclass
class ListItem:
    runs: list[Run] = field(default_factory=list)   # inline-formatted line

@dataclass
class ListBlock:
    ordered: bool                                    # True = <ol>, False = <ul>
    items: list[ListItem] = field(default_factory=list)

@dataclass
class Quote:
    runs: list[Run] = field(default_factory=list)
```

`Document.blocks` union widens to `Heading | Paragraph | Image | ListBlock | Quote`.

## Detection rules (parser — `src/parser.py`)

1. **Lists.** Add `"ul"`, `"ol"` to the `body.find_all([...], recursive=False)`
   scan. For each list, collect direct `<li>` children; run each `<li>`'s spans
   through the existing `_merge_spans` (inline bold/italic preserved). `ordered =
   (el.name == "ol")`. Drop empty items. Nested lists (level suffix `-0`/`-1`) are
   **out of scope v1** — flat lists only.
2. **Quotes.** Add a helper `yellow_class_set(html)` returning the CSS classes whose
   rule contains `background-color:#ffff00`. Kept separate from `style_class_sets`
   so its 2-tuple `(italic, bold)` contract — relied on by tests — is untouched. In
   `parse()`, for a `<p>`: if every non-empty direct `<span>` carries a yellow class
   → `Quote(runs=...)`, else `Paragraph`. Partial highlight within a paragraph stays
   a Paragraph (highlight dropped); whole-paragraph yellow → Quote.
3. **Order** is preserved by the single linear body scan, as today.

## VC adapter (`src/vc_adapter.py`) — after discovery

Discovery must establish three unknowns and record them in the experiments notes:

1. **List tool**: how ordered/unordered is selected (default is usually unordered —
   inline tune vs separate toolbox item), how Enter adds the next item, and how to
   **exit** the list (typically double-Enter on an empty item).
2. **Quote tool**: block structure — text field only, or also an author/caption
   field (left empty) — and how to exit the block.
3. **Trailing-Enter behavior**: the generic inter-block `Enter` (vc_adapter.py
   ~L116-117) creates a new *list item* inside a list, not a new block. So list/quote
   exit must happen *inside* the insert method, and the trailing Enter must be
   skipped/adjusted for these block types.

New methods (built only after discovery):

- `_insert_list(page, list_block)`: open toolbox → `data-type="list"` → switch to
  ordered if needed → type each item via `_type_runs`, Enter between items → exit.
- `_insert_quote(page, quote)`: open toolbox → `data-type="quote"` → `_type_runs`
  into the text field → author left empty → exit.
- `build_document` dispatch: add `isinstance(block, ListBlock)` and
  `isinstance(block, Quote)` branches; handle their trailing-Enter correctly.

Stability rule: if list/quote insertion proves async/flaky (as image upload did),
fix the real behavior with a `wait_for_*` predicate, not a `sleep`.

## Testing

**Offline unit tests (TDD, written before code):**

- `tests/test_parser_lists_quotes.py` against the real sample:
  - `ListBlock(ordered=True)` with 4 items; `ListBlock(ordered=False)` with 3 items;
    item texts match; correct position relative to neighbors.
  - `Quote` carrying the yellow text; neighboring blocks in order.
  - No empty items / no empty blocks.
- Synthetic mini-tests (not from file):
  - list item with a bold/italic span → inline formatting preserved in
    `ListItem.runs`;
  - paragraph with *partial* yellow → stays `Paragraph`; fully yellow → `Quote`;
  - `yellow_class_set` finds `background-color:#ffff00`, ignores other colors.
- Regression: existing parser/emitter tests stay green (`style_class_sets` contract
  untouched).

**Fixtures (required so offline tests can run):**

- Restore the original article as `example/170/index.html` (+ its `images/`) from git
  and repoint `tests/test_parser_example.py` at the new path.
- Place the new article at `example/lists-quotes/index.html` (+ its own `images/`),
  so the two articles do not share or clobber `images/`.
- This resolves the current `D index.html` / `?? Copyof.html` working-tree state.

**Live check (adapter):** one `run_vc.py` run on `example/lists-quotes/`, verifying by
eye that the ordered/unordered lists render correctly, the quote is a real quote
block, and block order matches the IR. The browser layer is not unit-tested.

## Milestones

1. **Fixtures.** Restore `example/170/`, move new article to `example/lists-quotes/`,
   repoint `test_parser_example.py`. Existing suite green.
2. **IR.** Add `ListItem`, `ListBlock`, `Quote`; widen `Document` union; extend
   `test_ir.py`.
3. **Parser — lists (TDD).** Tests first (real sample + synthetic inline), then code.
4. **Parser — quotes (TDD).** Tests first (`yellow_class_set`, full/partial yellow),
   then code.
5. **Discovery — VC.** Live pass on list/quote tools + trailing-Enter; record in
   `experiments/03-vc-editor/notes.md`.
6. **Adapter.** `_insert_list`, `_insert_quote`, dispatch branches, trailing-Enter;
   `wait_for_*` not `sleep`.
7. **Live end-to-end** on `example/lists-quotes/` — lists and quote correct, order = IR.

Steps 1–4 are deterministic and testable; the break to live-browser work is between
steps 4 and 5.

## Out of scope (v1)

Nested lists; partial inline highlight as quote; non-yellow highlight colors; quote
author field; other platforms (Habr / Dzen / Smartlab).

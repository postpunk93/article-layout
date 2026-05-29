# Two-Level Subheadings Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Carry two levels of subheadings (GDoc H2 → level-1, H3 → level-2) all the way from the parser through to the VC and Pikabu drafts, so subheadings stop disappearing.

**Architecture:** The parser preserves the real heading level in `Heading(level=N)` (H1 stays the article title). `emit_html` already renders `<h{level}>`. Each platform adapter renders the level using its own native control: VC picks the matching toolbox item, Pikabu relies on high-fidelity paste (with a per-node fallback if `<h3>` doesn't survive). A short discovery step confirms the unknown platform behaviour before the adapter work.

**Tech Stack:** Python, BeautifulSoup (parsing), Playwright (browser automation), pytest.

**Design:** `docs/plans/2026-05-29-heading-levels-design.md`

**Note on ordering:** Task 1 (parser) is pure and fully testable offline, so it goes first — it's the actual root of the bug. Discovery (Task 2) only gates the adapter tasks (3–4).

---

### Task 1: Parser recognises H3 as a level-3 heading

**Files:**
- Modify: `src/parser.py:122` (tag list) and `src/parser.py:142-147` (heading branch)
- Test: `tests/test_parser_blocks.py`

**Step 1: Write the failing tests**

Append to `tests/test_parser_blocks.py`:

```python
H3_DOC = """
<html><head><style>.c0{font-weight:400;font-style:normal}</style></head><body>
<h1 class="c6"><span class="c0">Title</span></h1>
<h2 class="c2"><span class="c0">Section</span></h2>
<h3 class="c3"><span class="c0">Subsection</span></h3>
<p class="c4"><span class="c0">body</span></p>
</body></html>
"""

# chernika-style doc: H3 used with no H2 above it. Content must NOT be dropped.
H3_ONLY = """
<html><head><style>.c0{font-weight:400;font-style:normal}</style></head><body>
<h1 class="c6"><span class="c0">T</span></h1>
<h3 class="c3"><span class="c0">Lonely sub</span></h3>
<p class="c4"><span class="c0">body</span></p>
</body></html>
"""


def test_h3_becomes_heading_level_3():
    doc = parse(H3_DOC)
    h3 = doc.blocks[1]
    assert isinstance(h3, Heading)
    assert h3.level == 3
    assert h3.runs[0].text == "Subsection"


def test_h2_and_h3_levels_and_order_preserved():
    doc = parse(H3_DOC)
    kinds = [(type(b).__name__, getattr(b, "level", None)) for b in doc.blocks]
    assert kinds == [("Heading", 2), ("Heading", 3), ("Paragraph", None)]


def test_h3_without_h2_is_still_parsed():
    doc = parse(H3_ONLY)
    assert isinstance(doc.blocks[0], Heading)
    assert doc.blocks[0].level == 3
    assert doc.blocks[0].runs[0].text == "Lonely sub"
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_parser_blocks.py -k "h3" -v`
Expected: FAIL — currently `<h3>` is skipped, so `doc.blocks[1]` is the paragraph (or IndexError) and no level-3 heading exists.

**Step 3: Write minimal implementation**

In `src/parser.py`, add `"h3"` to the tag list (line 122):

```python
    for el in body.find_all(["h1", "h2", "h3", "p", "ul", "ol"], recursive=False):
```

Replace the `h2`-only branch (lines 146–147):

```python
        if el.name == "h2":
            blocks.append(Heading(level=2, runs=runs))
```

with a level-derived branch:

```python
        if el.name in ("h2", "h3"):
            blocks.append(Heading(level=int(el.name[1]), runs=runs))
```

(The `else` paragraph/quote branch is unchanged — it now only ever sees `<p>`.)

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_parser_blocks.py -v`
Expected: PASS (new H3 tests + all existing block tests).

**Step 5: Run the full suite (guard against regressions)**

Run: `python -m pytest -q`
Expected: all green. (`test_parser_example` reads the real H3-only `example/170` fixture — confirm it no longer drops those headings.)

**Step 6: Commit**

```bash
git add src/parser.py tests/test_parser_blocks.py
git commit -m "fix(parser): parse h3 as level-3 heading (was silently dropped)"
```

---

### Task 2: Discovery — confirm how each platform produces two heading levels

The old notes (`experiments/04-pikabu-editor/notes.md:36`) claimed a single heading level; the editor screenshots disprove that (VC: «Подзаголовок H2 / H3»; Pikabu: «Заголовок 1 / 2»). Re-verify before touching adapters. **The user runs these (their login is required); Claude reads the dumped output.**

**Files:**
- Create: `experiments/05-heading-levels/probe_vc_headings.py`
- Create: `experiments/05-heading-levels/probe_pikabu_h3.py`
- Create: `experiments/05-heading-levels/notes.md` (findings, filled after the runs)

**Step 1: VC probe — dump the header toolbox items**

`probe_vc_headings.py` opens the VC editor (reusing the `.vc-profile` persistent context like `src/discover_vc.py`), opens the toolbox, and dumps every `.ce-toolbox__item` as `{data-type, text}` to stdout + `experiments/05-heading-levels/vc_toolbox.json`. Goal: learn the index/selector that yields H3 (expected: `[data-type="header"]` items in order `[0]=H2, [1]=H3`, but **confirm**).

**Step 2: Pikabu probe — does `<h3>` survive paste?**

`probe_pikabu_h3.py` opens the Pikabu editor (reusing `.pikabu-profile`), pastes `"<h2>Level two</h2><h3>Level three</h3>"` via the same synthetic-paste path as `pikabu_adapter._paste_html`, then dumps the resulting block tags (count of `h1/h2/h3` and each heading node's class) to stdout + `pikabu_after_paste.json`. Goal: confirm whether `<h3>` lands as «Заголовок 2» or is collapsed/dropped.

**Step 3: User runs both, Claude records findings**

Run (user): `python -m experiments.05-heading-levels.probe_vc_headings`
Run (user): `python -m experiments.05-heading-levels.probe_pikabu_h3`
Write the answers into `experiments/05-heading-levels/notes.md`:
- VC: exact selector/index for H3.
- Pikabu: does paste preserve `<h3>`? (decides whether Task 4 needs a fallback.)

**Step 4: Commit**

```bash
git add experiments/05-heading-levels/
git commit -m "experiment(05): discover two-level heading controls in VC + Pikabu"
```

---

### Task 3: VC adapter inserts the correct subheading level

**Files:**
- Modify: `src/vc_adapter.py:72-79` (`_insert_heading`) and its call site (~`src/vc_adapter.py:188-190`)

**Step 1: Add `level` parameter, select the matching toolbox item**

Replace `_insert_heading` (use the exact selector/index confirmed in Task 2 — the code below assumes `[0]=H2, [1]=H3`):

```python
def _insert_heading(page, runs, level):
    _open_toolbox(page)
    # Header toolbox items, in document order: [0]="Подзаголовок H2", [1]="Подзаголовок H3".
    idx = 0 if level <= 2 else 1
    page.eval_on_selector_all(
        '.ce-toolbox__item[data-type="header"]', f"els => els[{idx}].click()"
    )
    time.sleep(0.4)
    _type_runs(page, runs)
```

Update the call site in the block loop (currently `_insert_heading(page, block.runs)`):

```python
            _insert_heading(page, block.runs, block.level)
```

**Step 2: Verify end-to-end (user runs; manual visual check)**

Run (user): `python run_vc.py in/chernika` (or a small H2+H3 fixture)
Expected: H2 lines land as «Подзаголовок H2», H3 lines as «Подзаголовок H3»; block order intact; no headings missing.

**Step 3: Commit**

```bash
git add src/vc_adapter.py
git commit -m "feat(vc): insert level-2 and level-3 subheadings per IR level"
```

---

### Task 4: Pikabu renders both heading levels

`emit_html` already emits `<h2>`/`<h3>`, so the body paste carries both. **The path depends on Task 2's Pikabu finding:**

**Case A — paste preserves `<h3>` (expected):** no code change. Add a regression test that `emit_body` emits `<h3>` for a level-3 heading, then verify end-to-end.

`tests/test_emit_html.py`:

```python
def test_emit_heading_level_3():
    from src.ir import Document, Heading, Run
    doc = Document(title="t", blocks=[Heading(level=3, runs=[Run(text="Sub")])])
    assert "<h3>Sub</h3>" in emit_body(doc)
```

Run: `python -m pytest tests/test_emit_html.py -k level_3 -v` → PASS.
Run (user): `python run_pikabu.py in/chernika` → both heading levels present in the draft.

**Case B — paste collapses/drops `<h3>`:** add a per-heading-node fixup in `src/pikabu_adapter.py` after `_paste_html` — for each pasted heading, set its level via the editor's heading dropdown («Заголовок 1/2») using the selector found in Task 2. (Defer the exact code until Task 2 shows this is needed; do not write it speculatively — YAGNI.)

**Step — Commit**

```bash
git add tests/test_emit_html.py src/pikabu_adapter.py
git commit -m "feat(pikabu): render level-2 and level-3 subheadings"
```

---

### Task 5: Document the draft formatting convention

**Files:**
- Create: `docs/draft-formatting-convention.md`

**Step 1: Write the convention**

Document the source-of-truth rules so drafts are authored consistently (and so a copy-paste-from-Habr doc like `chernika` gets reformatted rather than silently mis-parsed):

- `Heading 1` = article title (exactly one; goes into the platform's title field).
- `Heading 2` = subheading level 1.
- `Heading 3` = subheading level 2.
- Yellow highlight = quote. *(existing)*
- Italic text directly under an image = caption. *(existing)*

Add a short note: `example/170` / `in/chernika` were pasted from Habr (H3-only) and don't follow this convention — reformat in GDoc when re-exporting.

**Step 2: Commit**

```bash
git add docs/draft-formatting-convention.md
git commit -m "docs: draft formatting convention (h1 title, h2/h3 subheadings)"
```

---

## After this plan

Return to the separate **repo-cleanup** task (already brainstormed, "archive" variant): move `experiments/*/notes.md` knowledge into `docs/`, delete one-off `probe_*`/`discover_*`/`explore_*` scripts (history stays in git).

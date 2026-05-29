# List + Blockquote Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Carry two GDoc conventions — lists (`<ul>`/`<ol>`) and yellow-highlight blockquotes — through the parser → IR → VC (Editor.js) adapter so they become real list and quote blocks in a VC draft.

**Architecture:** Three layers, unchanged. `src/parser.py` turns the GDoc "Web page (.html)" export into a platform-agnostic IR (`src/ir.py`); `src/vc_adapter.py` drives the VC Editor.js editor block-by-block. We add two IR block types, extend the parser's body scan + detection rules (deterministic, TDD'd offline against a real sample), then — after a short live discovery pass on VC's `list`/`quote` toolbox tools — add two adapter insert methods.

**Tech Stack:** Python 3.10, BeautifulSoup4 (parsing), Playwright (browser automation), pytest. Windows / PowerShell host; run pytest as `python -m pytest`.

**Design reference:** `docs/plans/2026-05-29-lists-and-quotes-design.md`

**Conventions in this repo (match them):**
- Tests live in `tests/`, import from `src.*`, and are plain pytest functions (no classes).
- Parser reuses `_merge_spans` to turn a block's direct `<span>` children into styled `Run`s.
- Commit messages: conventional-commit style (`feat:`, `test:`, `refactor:`, `chore:`), and end with the trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- All file reads/writes of GDoc HTML use `encoding="utf-8"` (the content is Cyrillic).

---

## Task 1: Reorganize fixtures into two articles

The working tree currently has `example/index.html` deleted and a new `example/Copyof.html` added (a different article that contains lists + a yellow quote). Two test files load `example/index.html` and will break. Give each article its own folder so they never share `images/`.

**Files:**
- Restore: `example/170/index.html` (the original article, from git `HEAD`)
- Move: `example/Copyof.html` → `example/lists-quotes/index.html`
- Move images: the original article's `images/` → `example/170/images/`; the new article's images → `example/lists-quotes/images/`
- Modify: `tests/test_parser_example.py:5` (path `example/index.html` → `example/170/index.html`)
- Modify: `tests/test_parser_styles.py:22` (path `example/index.html` → `example/170/index.html`)

**Step 1: Inspect what's in the working tree and in git**

```bash
git status --short
git show HEAD:example/index.html | head -5      # confirm original is recoverable
ls example/images | wc -l                        # how many images currently present
```

Note: the original article references `images/imageN.png` (10 images, `image1`..`image10`); the new article *also* references `image1`..`image10` but they are different files. The `images/` folder currently on disk belongs to whichever article the user last exported (the new one). The original images are recoverable from git.

**Step 2: Create folders and restore the original article**

```bash
mkdir -p example/170/images example/lists-quotes/images
git show HEAD:example/index.html > example/170/index.html
# restore the original images from HEAD (they were tracked under example/images/)
for n in $(seq 1 10); do git show "HEAD:example/images/image$n.png" > "example/170/images/image$n.png"; done
```

If any `git show` for an image fails (filename differs), list the tracked originals with `git ls-tree HEAD example/images/` and copy the actual names.

**Step 3: Move the new article into its own folder**

```bash
git mv example/Copyof.html example/lists-quotes/index.html 2>/dev/null || mv example/Copyof.html example/lists-quotes/index.html
# move the new article's images off the shared path into its folder
git mv example/images/* example/lists-quotes/images/ 2>/dev/null || mv example/images/* example/lists-quotes/images/
rmdir example/images 2>/dev/null || true
```

**Step 4: Repoint the two tests**

In `tests/test_parser_example.py`, change line 5:
```python
doc = parse(Path("example/170/index.html").read_text(encoding="utf-8"))
```

In `tests/test_parser_styles.py`, change line 22:
```python
EXAMPLE = Path("example/170/index.html").read_text(encoding="utf-8")
```

**Step 5: Run the full suite — must be green (no behavior change yet)**

Run: `python -m pytest -q`
Expected: all existing tests PASS (the 31 prior tests), 0 failures.

**Step 6: Commit**

```bash
git add -A
git commit -m "chore: split fixtures into example/170 and example/lists-quotes

Original article moved to example/170/; new list+quote sample to
example/lists-quotes/. Repoint test_parser_example and test_parser_styles.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Add IR block types

**Files:**
- Modify: `src/ir.py`
- Test: `tests/test_ir.py`

**Step 1: Write the failing test** (append to `tests/test_ir.py`)

```python
from src.ir import ListItem, ListBlock, Quote


def test_listblock_holds_ordered_flag_and_items():
    lb = ListBlock(ordered=True, items=[
        ListItem(runs=[Run("first", False, False)]),
        ListItem(runs=[Run("second", True, False)]),
    ])
    assert lb.ordered is True
    assert len(lb.items) == 2
    assert lb.items[1].runs[0].bold is True


def test_quote_holds_runs():
    q = Quote(runs=[Run("quoted", False, False)])
    assert q.runs[0].text == "quoted"
```

**Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_ir.py -q`
Expected: FAIL — `ImportError: cannot import name 'ListItem'`.

**Step 3: Implement** (add to `src/ir.py`, after `Image`)

```python
@dataclass
class ListItem:
    runs: list[Run] = field(default_factory=list)


@dataclass
class ListBlock:
    ordered: bool
    items: list[ListItem] = field(default_factory=list)


@dataclass
class Quote:
    runs: list[Run] = field(default_factory=list)
```

And widen the `Document.blocks` annotation:
```python
    blocks: list["Heading | Paragraph | Image | ListBlock | Quote"] = field(default_factory=list)
```

**Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_ir.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/ir.py tests/test_ir.py
git commit -m "feat: IR ListItem/ListBlock/Quote block types

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Parse lists (`<ul>`/`<ol>`) — synthetic TDD

Detect lists from real tags and preserve inline formatting per item.

**Files:**
- Modify: `src/parser.py` (the `parse()` body loop)
- Test: `tests/test_parser_lists.py` (create)

**Step 1: Write the failing test** (`tests/test_parser_lists.py`)

```python
from src.parser import parse
from src.ir import ListBlock, Paragraph

HTML = """
<html><head><style>
.c0{font-weight:400;font-style:normal}
.c1{font-weight:700}
.c8{font-style:italic}
</style></head><body>
<p class="c4"><span class="c0">intro</span></p>
<ul class="c11"><li class="c2"><span class="c0">Zara, </span></li>
<li class="c2"><span class="c1">bold item</span></li></ul>
<ol class="c11" start="1"><li class="c2"><span class="c0">step one</span></li>
<li class="c2"><span class="c8">step two</span></li>
<li class="c2"><span class="c0">step three</span></li></ol>
<p class="c4"><span class="c0">outro</span></p>
</body></html>
"""


def test_unordered_list_parsed_with_items():
    doc = parse(HTML)
    lists = [b for b in doc.blocks if isinstance(b, ListBlock)]
    ul = lists[0]
    assert ul.ordered is False
    assert [i.runs[0].text.strip() for i in ul.items] == ["Zara,", "bold item"]


def test_ordered_list_parsed_with_three_items():
    doc = parse(HTML)
    ol = [b for b in doc.blocks if isinstance(b, ListBlock)][1]
    assert ol.ordered is True
    assert len(ol.items) == 3


def test_list_item_preserves_inline_formatting():
    doc = parse(HTML)
    ul = [b for b in doc.blocks if isinstance(b, ListBlock)][0]
    assert ul.items[1].runs[0].bold is True       # "bold item"
    ol = [b for b in doc.blocks if isinstance(b, ListBlock)][1]
    assert ol.items[1].runs[0].italic is True      # "step two"


def test_lists_keep_position_between_paragraphs():
    doc = parse(HTML)
    kinds = [type(b).__name__ for b in doc.blocks]
    assert kinds == ["Paragraph", "ListBlock", "ListBlock", "Paragraph"]


def test_empty_list_items_dropped():
    html = HTML.replace('<li class="c2"><span class="c0">step three</span></li>',
                        '<li class="c2"><span></span></li>')
    doc = parse(html)
    ol = [b for b in doc.blocks if isinstance(b, ListBlock)][1]
    assert len(ol.items) == 2
```

**Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_parser_lists.py -q`
Expected: FAIL — lists currently produce no `ListBlock` (they are skipped by the body scan), so `lists[0]` raises `IndexError`.

**Step 3: Implement** in `src/parser.py`

Add a helper above `parse()`:
```python
def _parse_list(el, italic_classes, bold_classes):
    """Turn a <ul>/<ol> into a ListBlock. Inline formatting preserved per item;
    empty items dropped."""
    items = []
    for li in el.find_all("li", recursive=False):
        runs = _merge_spans(li.find_all("span", recursive=False), italic_classes, bold_classes)
        if runs:
            items.append(ListItem(runs=runs))
    return ListBlock(ordered=(el.name == "ol"), items=items)
```

In `parse()`, add `"ul"` and `"ol"` to the scan and handle them first in the loop:
```python
    for el in body.find_all(["h1", "h2", "p", "ul", "ol"], recursive=False):
        if el.name in ("ul", "ol"):
            lb = _parse_list(el, italic_classes, bold_classes)
            if lb.items:
                blocks.append(lb)
            continue
        if el.find("img") is not None:
            ...   # unchanged
```

Update the import line at top of `parser.py`:
```python
from src.ir import Run, Heading, Paragraph, Image, ListItem, ListBlock, Quote, Document
```
(`Quote` is imported now so Task 4 needs no further import edit.)

**Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_parser_lists.py -q`
Expected: PASS (5 tests).

**Step 5: Run the full suite (regression)**

Run: `python -m pytest -q`
Expected: all PASS.

**Step 6: Commit**

```bash
git add src/parser.py tests/test_parser_lists.py
git commit -m "feat: parse <ul>/<ol> into ListBlock, inline formatting per item

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Parse yellow-highlight paragraphs as quotes — synthetic TDD

**Files:**
- Modify: `src/parser.py` (add `yellow_class_set`, quote detection in `parse()`)
- Test: `tests/test_parser_quotes.py` (create)

**Step 1: Write the failing test** (`tests/test_parser_quotes.py`)

```python
from src.parser import parse, yellow_class_set
from src.ir import Quote, Paragraph

STYLE = (
    ".c0{font-weight:400;font-style:normal}"
    ".c10{background-color:#ffff00}"
    ".c13{background-color:#c9daf8}"
)


def test_yellow_class_set_finds_only_yellow():
    classes = yellow_class_set(f"<style>{STYLE}</style>")
    assert classes == {"c10"}


def test_fully_yellow_paragraph_is_quote():
    html = f"<html><head><style>{STYLE}</style></head><body>" \
           '<p class="c3"><span class="c0 c10">a real quote</span></p></body></html>'
    doc = parse(html)
    assert isinstance(doc.blocks[0], Quote)
    assert doc.blocks[0].runs[0].text == "a real quote"


def test_partial_yellow_paragraph_stays_paragraph():
    html = f"<html><head><style>{STYLE}</style></head><body>" \
           '<p class="c3"><span class="c0">plain </span>' \
           '<span class="c0 c10">highlit</span></p></body></html>'
    doc = parse(html)
    assert isinstance(doc.blocks[0], Paragraph)


def test_non_yellow_highlight_is_not_a_quote():
    html = f"<html><head><style>{STYLE}</style></head><body>" \
           '<p class="c3"><span class="c0 c13">blue</span></p></body></html>'
    doc = parse(html)
    assert isinstance(doc.blocks[0], Paragraph)
```

**Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_parser_quotes.py -q`
Expected: FAIL — `ImportError: cannot import name 'yellow_class_set'`.

**Step 3: Implement** in `src/parser.py`

Add the helper (near `style_class_sets`):
```python
def yellow_class_set(html: str):
    """Return the set of CSS classes whose rule sets background-color:#ffff00."""
    soup = BeautifulSoup(html, "html.parser")
    css = "\n".join(s.get_text() for s in soup.find_all("style"))
    yellow = set()
    for name, body in re.findall(r"\.(c\d+)\s*\{([^}]*)\}", css):
        if "background-color:#ffff00" in re.sub(r"\s+", "", body):
            yellow.add(name)
    return yellow
```

Add a predicate:
```python
def _is_yellow_quote(p, yellow_classes):
    """True if every non-empty direct <span> of p carries a yellow class."""
    spans = [s for s in p.find_all("span", recursive=False) if s.get_text().strip()]
    if not spans:
        return False
    return all(any(c in yellow_classes for c in s.get("class", [])) for s in spans)
```

In `parse()`: compute `yellow_classes = yellow_class_set(html)` next to the existing `style_class_sets` call, then in the `<p>` branch (after the image check, before/at the paragraph-vs-heading decision) handle quotes. The `p` branch currently does `runs = spans_to_runs(...)`; insert before appending a `Paragraph`:
```python
        if el.name == "p" and _is_yellow_quote(el, yellow_classes):
            blocks.append(Quote(runs=runs))
            continue
```
Place this so it only affects `<p>` (not `h1`/`h2`), and after the `if not runs: continue` guard.

**Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_parser_quotes.py -q`
Expected: PASS (4 tests).

**Step 5: Run the full suite (regression)**

Run: `python -m pytest -q`
Expected: all PASS.

**Step 6: Commit**

```bash
git add src/parser.py tests/test_parser_quotes.py
git commit -m "feat: yellow-highlight paragraph parsed as Quote block

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: End-to-end parser test on the real sample

Pin the real `example/lists-quotes/index.html` to lock detection against real markup.

**Files:**
- Test: `tests/test_parser_lists_quotes_example.py` (create)

**Step 1: Read the real sample to get exact item/quote text**

Open `example/lists-quotes/index.html` in an editor (UTF-8) and read off:
- the unordered list's 3 items (first is `"Zara,"`),
- the ordered list's 4 items,
- the yellow quote's text.

Fill the exact Cyrillic strings into the asserts below where marked. (The console may mojibake Cyrillic — copy from the editor, not a terminal dump.)

**Step 2: Write the test**

```python
from pathlib import Path
from src.parser import parse
from src.ir import ListBlock, Quote

doc = parse(Path("example/lists-quotes/index.html").read_text(encoding="utf-8"))
LISTS = [b for b in doc.blocks if isinstance(b, ListBlock)]
QUOTES = [b for b in doc.blocks if isinstance(b, Quote)]


def test_two_lists_one_unordered_one_ordered():
    assert len(LISTS) == 2
    assert LISTS[0].ordered is False          # <ul> appears first in the doc
    assert LISTS[1].ordered is True           # <ol> second


def test_unordered_list_has_three_items_starting_zara():
    ul = LISTS[0]
    assert len(ul.items) == 3
    assert ul.items[0].runs[0].text.strip() == "Zara,"


def test_ordered_list_has_four_items():
    assert len(LISTS[1].items) == 4
    # OPTIONAL strengthening: assert exact Cyrillic item texts read in Step 1
    # assert LISTS[1].items[0].runs[0].text.strip() == "<exact text>"


def test_one_quote_present_and_nonempty():
    assert len(QUOTES) == 1
    text = "".join(r.text for r in QUOTES[0].runs).strip()
    assert len(text) > 0
    # OPTIONAL strengthening: assert text.startswith("<exact quote prefix>")


def test_no_empty_list_items():
    for lb in LISTS:
        assert all("".join(r.text for r in it.runs).strip() for it in lb.items)
```

**Step 3: Run**

Run: `python -m pytest tests/test_parser_lists_quotes_example.py -q`
Expected: PASS (5 tests). If counts differ, re-inspect the sample and fix the asserts to match reality (the sample is ground truth).

**Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: all PASS.

**Step 5: Commit**

```bash
git add tests/test_parser_lists_quotes_example.py
git commit -m "test: end-to-end parser check for lists+quote on real sample

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Discover VC list + quote editor interaction

The VC editor is Editor.js. The toolbox exposes `data-type="list"` and `data-type="quote"` (confirmed). The exact interaction is NOT yet known — discover it live before writing adapter code. This task produces NOTES ONLY (no adapter code yet).

**Files:**
- Modify: `experiments/03-vc-editor/notes.md` (append a "Lists & Quotes" section)

**Prereq:** the `.vc-profile` is logged in (the user logged in by hand once). If not, the editor won't open — pause and ask the user to log in.

**Step 1: Open the editor with the existing discovery harness**

Use the existing approach in `src/discover_vc.py` / `experiments/03-vc-editor/` to open `https://vc.ru/?modal=editor` with the persistent `.vc-profile`, headed. Manually (or via the snapshot tool) determine and record:

1. **List tool**
   - After clicking `+` and the `list` toolbox item, what DOM appears? (block class, the editable element selector)
   - Is the default ordered or unordered? How do you switch? (an inline settings/tune button, a second toolbox item, or a keyboard toggle) — record the exact selector / gesture.
   - Does pressing Enter inside an item create the next item? How do you EXIT the list (double-Enter on an empty item? Enter then Backspace?) — record exactly.
2. **Quote tool**
   - After clicking the `quote` toolbox item, record the block structure: the text-field selector, and whether there is a separate author/caption field (which we leave empty).
   - How do you exit the quote block to continue with the next block?
3. **Trailing-Enter interaction**
   - Confirm that the generic inter-block `Enter` in `build_document` (vc_adapter.py ~L116-117) would land *inside* a list/quote. Record what the insert method must do to leave the block cleanly so the next block starts fresh.

**Step 2: Write the notes**

Append a clearly-headed "Lists & Quotes (discovered <date>)" section to `experiments/03-vc-editor/notes.md` with exact selectors and gestures for each of the three points above. Include any `wait_for_*` predicate needed (e.g. wait until the list block exists) if the interaction is async.

**Step 3: Commit**

```bash
git add experiments/03-vc-editor/notes.md
git commit -m "experiment(03): record VC list + quote tool interaction

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Adapter — insert lists and quotes

Implement against the selectors/gestures recorded in Task 6. Replace any `<PLACEHOLDER>` below with the discovered values.

**Files:**
- Modify: `src/vc_adapter.py`

**Step 1: Add insert helpers** (model them on `_insert_heading` / `_insert_image`)

```python
def _insert_list(page, list_block):
    _open_toolbox(page)
    page.eval_on_selector('.ce-toolbox__item[data-type="list"]', "el => el.click()")
    time.sleep(0.4)
    # Switch ordered/unordered if needed (per discovery):
    if list_block.ordered:
        ...  # <discovered gesture to switch to ordered>
    for i, item in enumerate(list_block.items):
        _type_runs(page, item.runs)
        if i < len(list_block.items) - 1:
            page.keyboard.press("Enter")   # next item
    # <discovered gesture to EXIT the list cleanly>


def _insert_quote(page, quote):
    _open_toolbox(page)
    page.eval_on_selector('.ce-toolbox__item[data-type="quote"]', "el => el.click()")
    time.sleep(0.4)
    # focus the quote text field if needed (per discovery), then:
    _type_runs(page, quote.runs)
    # author field left empty; <discovered gesture to EXIT the quote block>
```

**Step 2: Dispatch in `build_document`**

Update the import:
```python
from src.ir import Heading, Paragraph, Image, ListBlock, Quote
```
Add branches in the block loop (alongside the existing `isinstance` checks):
```python
        elif isinstance(block, ListBlock):
            log(f"[{i}] list ordered={block.ordered} items={len(block.items)}")
            _insert_list(page, block)
        elif isinstance(block, Quote):
            log(f"[{i}] quote ({len(block.runs)} runs)")
            _insert_quote(page, block)
```

**Step 3: Handle the trailing-Enter for these block types**

If discovery showed the insert method already exits the block, the generic `if i < last: page.keyboard.press("Enter")` may add an unwanted extra block after a list/quote. Adjust per discovery — e.g. skip the generic Enter when the block was a `ListBlock`/`Quote` because the exit gesture already created the next empty block. Keep the existing "no trailing Enter after the last block" behavior.

**Step 4: Commit (code only; live verification is Task 8)**

```bash
git add src/vc_adapter.py
git commit -m "feat(vc): insert list and quote blocks in Editor.js

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Live end-to-end verification

**Files:** none (verification + possible fixups in `src/vc_adapter.py`).

**Step 1: Stage the sample as an input**

The runner takes `in/<slug>` with `index.html` + `images/`. Copy the fixture in:
```bash
mkdir -p in/lists-quotes
cp example/lists-quotes/index.html in/lists-quotes/index.html
cp -r example/lists-quotes/images in/lists-quotes/images
```
(Confirm the exact `in/<slug>` layout `run_vc.py` expects; mirror what `example/170` → existing `in/` usage does.)

**Step 2: Run the pipeline**

Run: `python run_vc.py in/lists-quotes`
A headed browser opens, builds the draft, stops at a saved draft (URL gains `id=`).

**Step 3: Verify by eye in the browser**
- The unordered list is an unordered list with 3 items; the ordered list is ordered with 4 items.
- The yellow paragraph is a real quote block.
- Block ORDER matches the IR (lists/quote in the right place relative to surrounding text/images). This is the regression that bit the image flow — confirm explicitly.

**Step 4: If order/format is wrong**

Do NOT add `sleep`. If insertion is async, add a `wait_for_function`/`wait_for_selector` predicate (model it on `_insert_image`'s wait for the uploaded `<img>`). Fix, re-run Step 2, re-verify. Commit each fix:
```bash
git add src/vc_adapter.py
git commit -m "fix(vc): <specific fix> for list/quote insertion

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**Step 5: Final regression**

Run: `python -m pytest -q`
Expected: all PASS.

---

## Out of scope (v1)

Nested lists; partial inline highlight as quote; non-yellow highlight colors; quote author field; other platforms (Habr / Dzen / Smartlab). Known v1 follow-up carried over: caption runs are still flattened (inline formatting dropped) — not addressed here.

## Definition of done

- All unit tests green (`python -m pytest -q`).
- One live VC draft built from `example/lists-quotes` with correct unordered list, ordered list, and quote block, in correct document order.
- `experiments/03-vc-editor/notes.md` documents the list/quote interaction.

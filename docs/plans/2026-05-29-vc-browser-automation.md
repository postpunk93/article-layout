# VC Browser Automation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Take a standard unpacked Google Docs zip (`in/<slug>/index.html` + `images/`) and, via Python + Playwright, fill the VC.ru editor and save a draft — images included.

**Architecture:** Three layers. (1) A BeautifulSoup parser turns the messy GDoc HTML into a clean platform-agnostic block model (IR). (2) An HTML emitter renders the IR to clean body HTML with `[[IMG:name]]` markers where images go. (3) A Playwright VC adapter (saved browser profile, visible window) pastes the body, uploads each image file into its marker via the editor's native file input, fills captions, and stops at a saved draft. A discovery phase records the real VC selectors and paste mechanism before the adapter is written.

**Tech Stack:** Python 3, Playwright (Chromium, persistent context), BeautifulSoup4, pytest.

**Design doc:** `docs/plans/2026-05-29-vc-browser-automation-design.md`

---

## Reference facts from `example/index.html` (already inspected)

Use these as test fixtures and parser assumptions.

- **Italic classes:** `.c3`, `.c5`, `.c8` — each rule contains `font-style:italic`.
- **Bold classes:** `.c1`, `.c9`, `.c10` — each rule contains `font-weight:700`.
- **Normal:** `.c0` (explicitly `font-weight:400;font-style:normal`) and spans with **no** class.
- **Highlight classes (unused in this article, deferred):** `.c7` = `#c9daf8`, `.c11` = `#f4cccc`.
- **Block padding classes (block-level, ignore for style):** `.c2`, `.c4`, `.c6`, `.c12`.
- **Headings:** `<h1 class="c6">` (the single article title), `<h2 class="c2">` (section headers).
- **Image-in-paragraph markup:**
  ```
  <p class="c4">
    <span style="...overflow:hidden;..."><img alt="" src="images/imageN.png" style="..." title=""></span>
    <span><br></span>
    <span class="cX">caption text?</span>
  </p>
  ```
- **Caption fixtures (contrasting):**
  - `image8.png` → trailing span class `c3` (italic) text `"Первый набросок устройства, конец 2"` → **caption**.
  - `image5.png` → trailing span class `c0` (normal) text `"Это я)"` → **NOT a caption**; emit as a standalone paragraph.
- **Standalone image (no trailing text in same `<p>`):** `image9.png`, `image2.png` — img is alone in its `<p>`; the following `<p>` is normal `c0` text → that following `<p>` is its own paragraph (NOT consumed as caption).

**Caption rule for v1 (YAGNI):** only inspect trailing text **inside the same `<p>` as the image** (after the `<br>`). If that trailing text exists and **every run in it is italic** → caption. Otherwise the image has no caption and any trailing text becomes a standalone paragraph. The "caption in the *next* `<p>`" variant is deferred until a real article needs it (no fixture exists).

---

## Task 1: Project setup

**Files:**
- Create: `requirements.txt`
- Modify: `.gitignore`
- Create: `src/__init__.py`, `tests/__init__.py`

**Step 1: Create `requirements.txt`**

```
beautifulsoup4
playwright
pytest
```

**Step 2: Add the browser profile dir to `.gitignore`**

Append these lines to `.gitignore`:

```
.vc-profile/
__pycache__/
.pytest_cache/
```

**Step 3: Create empty package markers**

Create `src/__init__.py` (empty) and `tests/__init__.py` (empty).

**Step 4: Install dependencies**

Run: `python -m pip install -r requirements.txt`
Then: `python -m playwright install chromium`
Expected: pip reports success; Playwright downloads Chromium.

**Step 5: Verify pytest runs**

Run: `python -m pytest -q`
Expected: "no tests ran" (exit 5) — confirms pytest is installed.

**Step 6: Commit**

```bash
git add requirements.txt .gitignore src/__init__.py tests/__init__.py
git commit -m "chore: project setup for VC automation (playwright, bs4, pytest)"
```

---

## Task 2: IR dataclasses

**Files:**
- Create: `src/ir.py`
- Test: `tests/test_ir.py`

**Step 1: Write the failing test**

```python
# tests/test_ir.py
from src.ir import Run, Heading, Paragraph, Image, Document


def test_document_holds_title_and_blocks():
    doc = Document(
        title="My Title",
        blocks=[
            Heading(level=2, runs=[Run("Section", bold=False, italic=False)]),
            Paragraph(runs=[Run("hello ", False, False), Run("world", False, True)]),
            Image(file="image5.png", caption=None),
            Image(file="image8.png", caption=[Run("cap", False, True)]),
        ],
    )
    assert doc.title == "My Title"
    assert doc.blocks[1].runs[1].italic is True
    assert doc.blocks[2].caption is None
    assert doc.blocks[3].caption[0].text == "cap"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ir.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.ir'`.

**Step 3: Write minimal implementation**

```python
# src/ir.py
from dataclasses import dataclass, field


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False


@dataclass
class Heading:
    level: int
    runs: list = field(default_factory=list)


@dataclass
class Paragraph:
    runs: list = field(default_factory=list)


@dataclass
class Image:
    file: str
    caption: list | None = None  # list[Run] or None


@dataclass
class Document:
    title: str
    blocks: list = field(default_factory=list)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ir.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/ir.py tests/test_ir.py
git commit -m "feat: IR dataclasses (Run, Heading, Paragraph, Image, Document)"
```

---

## Task 3: Parse the stylesheet into italic/bold class sets

**Files:**
- Create: `src/parser.py`
- Test: `tests/test_parser_styles.py`

**Step 1: Write the failing test**

```python
# tests/test_parser_styles.py
from src.parser import style_class_sets

STYLE = (
    '.c0{color:#000;font-weight:400;font-style:normal}'
    '.c1{font-weight:700;font-style:normal}'
    '.c3{font-weight:400;font-style:italic}'
    '.c8{font-style:italic}'
    '.c10{font-size:23pt;font-weight:700}'
)


def test_style_class_sets_finds_italic_and_bold():
    italic, bold = style_class_sets(f'<style>{STYLE}</style>')
    assert italic == {"c3", "c8"}
    assert bold == {"c1", "c10"}
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_parser_styles.py -v`
Expected: FAIL — `cannot import name 'style_class_sets'`.

**Step 3: Write minimal implementation**

```python
# src/parser.py
import re
from bs4 import BeautifulSoup


def style_class_sets(html: str):
    """Return (italic_classes, bold_classes) by scanning the <style> block.

    A class is italic if its rule contains font-style:italic.
    A class is bold if its rule contains font-weight:700.
    """
    soup = BeautifulSoup(html, "html.parser")
    style = soup.find("style")
    css = style.get_text() if style else ""
    italic, bold = set(), set()
    for name, body in re.findall(r"\.(c\d+)\s*\{([^}]*)\}", css):
        decls = body.replace(" ", "")
        if "font-style:italic" in decls:
            italic.add(name)
        if "font-weight:700" in decls:
            bold.add(name)
    return italic, bold
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_parser_styles.py -v`
Expected: PASS.

**Step 5: Add a test against the real example file**

```python
# append to tests/test_parser_styles.py
from pathlib import Path

EXAMPLE = Path("example/index.html").read_text(encoding="utf-8")


def test_style_class_sets_on_real_example():
    italic, bold = style_class_sets(EXAMPLE)
    assert {"c3", "c5", "c8"}.issubset(italic)
    assert {"c1", "c9", "c10"}.issubset(bold)
```

**Step 6: Run both tests**

Run: `python -m pytest tests/test_parser_styles.py -v`
Expected: PASS (both).

**Step 7: Commit**

```bash
git add src/parser.py tests/test_parser_styles.py
git commit -m "feat: parse GDoc stylesheet into italic/bold class sets"
```

---

## Task 4: Merge a block's spans into runs

**Files:**
- Modify: `src/parser.py`
- Test: `tests/test_parser_runs.py`

**Step 1: Write the failing test**

```python
# tests/test_parser_runs.py
from bs4 import BeautifulSoup
from src.parser import spans_to_runs

ITALIC = {"c3", "c5", "c8"}
BOLD = {"c1", "c9", "c10"}


def _p(html):
    return BeautifulSoup(html, "html.parser").find("p")


def test_merges_adjacent_same_style_spans():
    p = _p('<p><span class="c0">Hello </span><span class="c0">world</span></p>')
    runs = spans_to_runs(p, ITALIC, BOLD)
    assert len(runs) == 1
    assert runs[0].text == "Hello world"
    assert runs[0].bold is False and runs[0].italic is False


def test_distinguishes_italic_run():
    p = _p('<p><span class="c0">plain </span><span class="c8">italic</span></p>')
    runs = spans_to_runs(p, ITALIC, BOLD)
    assert len(runs) == 2
    assert runs[1].italic is True


def test_classless_span_is_normal_and_entities_decoded():
    p = _p('<p><span>caf&eacute;</span></p>')
    runs = spans_to_runs(p, ITALIC, BOLD)
    assert runs[0].text == "café"
    assert runs[0].bold is False and runs[0].italic is False
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_parser_runs.py -v`
Expected: FAIL — `cannot import name 'spans_to_runs'`.

**Step 3: Write minimal implementation**

Add to `src/parser.py`:

```python
from src.ir import Run


def _span_style(span, italic_classes, bold_classes):
    classes = span.get("class", []) if hasattr(span, "get") else []
    italic = any(c in italic_classes for c in classes)
    bold = any(c in bold_classes for c in classes)
    return bold, italic


def spans_to_runs(block, italic_classes, bold_classes):
    """Flatten a block's <span> children into merged Run objects.

    Adjacent runs with identical (bold, italic) are concatenated.
    <br>-only spans contribute no text. Empty text is skipped.
    """
    runs = []
    for span in block.find_all("span", recursive=False):
        text = span.get_text()  # decodes entities; <br> yields ""/newline
        if text == "" or text is None:
            continue
        bold, italic = _span_style(span, italic_classes, bold_classes)
        if runs and runs[-1].bold == bold and runs[-1].italic == italic:
            runs[-1].text += text
        else:
            runs.append(Run(text=text, bold=bold, italic=italic))
    # drop runs that are only whitespace produced by <br>
    runs = [r for r in runs if r.text.strip() != "" or r.text == " "]
    return runs
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_parser_runs.py -v`
Expected: PASS (all three).

**Step 5: Commit**

```bash
git add src/parser.py tests/test_parser_runs.py
git commit -m "feat: merge GDoc spans into styled runs"
```

---

## Task 5: Classify blocks and extract the title (no images yet)

**Files:**
- Modify: `src/parser.py`
- Test: `tests/test_parser_blocks.py`

**Step 1: Write the failing test**

```python
# tests/test_parser_blocks.py
from src.parser import parse
from src.ir import Heading, Paragraph

HTML = """
<html><head><style>
.c0{font-weight:400;font-style:normal}
.c8{font-style:italic}
.c1{font-weight:700}
</style></head><body>
<h1 class="c6"><span class="c1">My </span><span class="c1">Title</span></h1>
<h2 class="c2"><span class="c1">Section One</span></h2>
<p class="c4"><span class="c0">Plain text </span><span class="c8">italic bit</span></p>
<p class="c4"><span></span></p>
</body></html>
"""


def test_first_h1_becomes_title():
    doc = parse(HTML)
    assert doc.title == "My Title"


def test_h2_becomes_heading_block():
    doc = parse(HTML)
    assert isinstance(doc.blocks[0], Heading)
    assert doc.blocks[0].level == 2
    assert doc.blocks[0].runs[0].text == "Section One"


def test_paragraph_runs_and_empty_dropped():
    doc = parse(HTML)
    assert isinstance(doc.blocks[1], Paragraph)
    assert doc.blocks[1].runs[0].text == "Plain text "
    assert doc.blocks[1].runs[1].italic is True
    # the empty <p> produced no block
    assert len(doc.blocks) == 2
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_parser_blocks.py -v`
Expected: FAIL — `cannot import name 'parse'`.

**Step 3: Write minimal implementation**

Add to `src/parser.py`:

```python
from src.ir import Heading, Paragraph, Document


def _runs_text(runs):
    return "".join(r.text for r in runs).strip()


def parse(html: str) -> Document:
    italic_classes, bold_classes = style_class_sets(html)
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    title = ""
    blocks = []
    for el in body.find_all(["h1", "h2", "p"], recursive=True):
        if el.find("img") is not None:
            continue  # images handled in Task 6
        runs = spans_to_runs(el, italic_classes, bold_classes)
        if not runs:
            continue
        if el.name == "h1":
            if not title:
                title = _runs_text(runs)
            continue
        if el.name == "h2":
            blocks.append(Heading(level=2, runs=runs))
        else:
            blocks.append(Paragraph(runs=runs))
    return Document(title=title, blocks=blocks)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_parser_blocks.py -v`
Expected: PASS (all three).

**Step 5: Commit**

```bash
git add src/parser.py tests/test_parser_blocks.py
git commit -m "feat: classify h1/h2/p blocks and extract entry title"
```

---

## Task 6: Images and the italic-caption rule

**Files:**
- Modify: `src/parser.py`
- Test: `tests/test_parser_images.py`

**Step 1: Write the failing test**

```python
# tests/test_parser_images.py
from src.parser import parse
from src.ir import Image, Paragraph

STYLE = """<style>
.c0{font-weight:400;font-style:normal}
.c3{font-style:italic}
</style>"""

# image followed by ITALIC trailing text in the same <p> -> caption
CAPTIONED = f"""<html><head>{STYLE}</head><body>
<p class="c4"><span><img src="images/image8.png"></span><span><br></span><span class="c3">Set sketch, take 2</span></p>
</body></html>"""

# image followed by NORMAL trailing text in the same <p> -> no caption + standalone paragraph
UNCAPTIONED = f"""<html><head>{STYLE}</head><body>
<p class="c4"><span><img src="images/image5.png"></span><span class="c0"><br>This is me)</span></p>
</body></html>"""

# image alone in its <p>
ALONE = f"""<html><head>{STYLE}</head><body>
<p class="c4"><span><img src="images/image9.png"></span></p>
<p class="c4"><span class="c0">Regular following paragraph.</span></p>
</body></html>"""


def test_italic_trailing_text_becomes_caption():
    doc = parse(CAPTIONED)
    assert isinstance(doc.blocks[0], Image)
    assert doc.blocks[0].file == "image8.png"
    assert doc.blocks[0].caption is not None
    assert doc.blocks[0].caption[0].text == "Set sketch, take 2"
    assert len(doc.blocks) == 1


def test_normal_trailing_text_is_standalone_paragraph():
    doc = parse(UNCAPTIONED)
    assert isinstance(doc.blocks[0], Image)
    assert doc.blocks[0].caption is None
    assert isinstance(doc.blocks[1], Paragraph)
    assert doc.blocks[1].runs[0].text.strip() == "This is me)"


def test_image_alone_then_normal_paragraph():
    doc = parse(ALONE)
    assert isinstance(doc.blocks[0], Image)
    assert doc.blocks[0].caption is None
    assert isinstance(doc.blocks[1], Paragraph)
    assert doc.blocks[1].runs[0].text == "Regular following paragraph."
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_parser_images.py -v`
Expected: FAIL — images are currently skipped, so `doc.blocks[0]` is not an `Image`.

**Step 3: Write minimal implementation**

In `src/parser.py`, replace the `if el.find("img") is not None: continue` branch with a real handler. Full revised loop body:

```python
import os
from src.ir import Image


def _trailing_runs_after_img(p, italic_classes, bold_classes):
    """Runs from spans that appear AFTER the <img> within the same <p>."""
    img = p.find("img")
    runs = []
    after = False
    for span in p.find_all("span", recursive=False):
        if span.find("img") is not None:
            after = True
            continue
        if not after:
            continue
        text = span.get_text()
        if text is None or text.strip() == "":
            continue
        bold = any(c in bold_classes for c in span.get("class", []))
        italic = any(c in italic_classes for c in span.get("class", []))
        if runs and runs[-1].bold == bold and runs[-1].italic == italic:
            runs[-1].text += text
        else:
            runs.append(Run(text=text, bold=bold, italic=italic))
    return runs
```

Then change the `for el in ...` loop so the image branch builds blocks:

```python
        if el.find("img") is not None:
            img = el.find("img")
            file = os.path.basename(img.get("src", ""))
            trailing = _trailing_runs_after_img(el, italic_classes, bold_classes)
            if trailing and all(r.italic for r in trailing):
                blocks.append(Image(file=file, caption=trailing))
            else:
                blocks.append(Image(file=file, caption=None))
                if trailing:
                    blocks.append(Paragraph(runs=trailing))
            continue
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_parser_images.py -v`
Expected: PASS (all three).

**Step 5: Run the whole suite (no regressions)**

Run: `python -m pytest -q`
Expected: all green.

**Step 6: Commit**

```bash
git add src/parser.py tests/test_parser_images.py
git commit -m "feat: parse images with italic-keyed caption rule"
```

---

## Task 7: End-to-end parse of the real example

**Files:**
- Test: `tests/test_parser_example.py`

**Step 1: Write the test**

```python
# tests/test_parser_example.py
from pathlib import Path
from src.parser import parse
from src.ir import Image, Heading, Paragraph

doc = parse(Path("example/index.html").read_text(encoding="utf-8"))


def test_title_extracted():
    assert "170" in doc.title  # H1 spans "1"/"7"/"0..." merge into the title


def test_all_ten_images_present():
    files = [b.file for b in doc.blocks if isinstance(b, Image)]
    assert sorted(files) == sorted(f"image{i}.png" for i in range(1, 11))


def test_image8_has_italic_caption():
    img8 = next(b for b in doc.blocks if isinstance(b, Image) and b.file == "image8.png")
    assert img8.caption is not None
    assert "набросок" in img8.caption[0].text


def test_image5_has_no_caption():
    img5 = next(b for b in doc.blocks if isinstance(b, Image) and b.file == "image5.png")
    assert img5.caption is None


def test_no_empty_blocks():
    for b in doc.blocks:
        if isinstance(b, (Heading, Paragraph)):
            assert "".join(r.text for r in b.runs).strip() != ""
```

**Step 2: Run test**

Run: `python -m pytest tests/test_parser_example.py -v`
Expected: PASS. If `image5`/`image8` assertions fail, inspect the actual trailing markup with:
`python -c "from src.parser import parse; from pathlib import Path; d=parse(Path('example/index.html').read_text(encoding='utf-8')); print([(b.file,b.caption) for b in d.blocks if hasattr(b,'file')])"`
and adjust `_trailing_runs_after_img` (e.g. handle the `<br>` living inside the same span as the caption text, as in `image5`'s `<span class="c0"><br>This is me)</span>`).

**Step 3: Commit**

```bash
git add tests/test_parser_example.py
git commit -m "test: end-to-end parser checks on the real example article"
```

---

## Task 8: Emit clean body HTML with image markers

**Files:**
- Create: `src/emit_html.py`
- Test: `tests/test_emit_html.py`

**Step 1: Write the failing test**

```python
# tests/test_emit_html.py
from src.ir import Document, Heading, Paragraph, Image, Run
from src.emit_html import emit_body


def test_emit_headings_paragraphs_formatting_and_markers():
    doc = Document(
        title="T",
        blocks=[
            Heading(level=2, runs=[Run("Sec", False, False)]),
            Paragraph(runs=[Run("a ", False, False), Run("bold", True, False), Run(" ", False, False), Run("it", False, True)]),
            Image(file="image5.png", caption=None),
            Image(file="image8.png", caption=[Run("cap", False, True)]),
        ],
    )
    html = emit_body(doc)
    assert "<h2>Sec</h2>" in html
    assert "<strong>bold</strong>" in html
    assert "<em>it</em>" in html
    assert "[[IMG:image5.png]]" in html
    assert "[[IMG:image8.png]]" in html


def test_html_special_chars_escaped():
    doc = Document(title="T", blocks=[Paragraph(runs=[Run("a < b & c", False, False)])])
    html = emit_body(doc)
    assert "a &lt; b &amp; c" in html
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_emit_html.py -v`
Expected: FAIL — `No module named 'src.emit_html'`.

**Step 3: Write minimal implementation**

```python
# src/emit_html.py
from html import escape
from src.ir import Heading, Paragraph, Image


def _runs_html(runs):
    out = []
    for r in runs:
        text = escape(r.text)
        if r.bold:
            text = f"<strong>{text}</strong>"
        if r.italic:
            text = f"<em>{text}</em>"
        out.append(text)
    return "".join(out)


def emit_body(doc):
    """Render IR blocks to clean body HTML.

    Images are NOT emitted as <img>; they become a visible marker
    paragraph [[IMG:file]] that the VC adapter later replaces with a
    real uploaded image. Captions are emitted as a marker too so the
    adapter can attach them after upload.
    """
    parts = []
    for b in doc.blocks:
        if isinstance(b, Heading):
            parts.append(f"<h{b.level}>{_runs_html(b.runs)}</h{b.level}>")
        elif isinstance(b, Paragraph):
            parts.append(f"<p>{_runs_html(b.runs)}</p>")
        elif isinstance(b, Image):
            parts.append(f"<p>[[IMG:{b.file}]]</p>")
            if b.caption:
                cap = "".join(r.text for r in b.caption)
                parts.append(f"<p>[[CAP:{escape(cap)}]]</p>")
    return "\n".join(parts)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_emit_html.py -v`
Expected: PASS (both).

**Step 5: Commit**

```bash
git add src/emit_html.py tests/test_emit_html.py
git commit -m "feat: emit clean body HTML with image/caption markers"
```

---

## Task 9: VC editor discovery (manual, exploratory — NOT TDD)

> This task produces recorded facts, not automated tests. The VC editor DOM is unknown and changes; do not guess selectors. Do this WITH the user — they offered to help. Each `<...>` in the notes template must be filled with a real observed value before Task 10.

**Files:**
- Create: `src/discover_vc.py`
- Create: `experiments/03-vc-editor/notes.md`

**Step 1: Create the notes template**

```markdown
# Experiment 03 — VC editor discovery

**Date:** <fill>
**Goal:** record real selectors + the working paste mechanism before writing the adapter.

## New-entry navigation
- URL of the "write new entry" page: <fill>
- How to detect logged-out state (selector/text): <fill>
- How to detect a saved draft (URL change / toast / autosave indicator): <fill>

## Selectors
- Title field: <fill>
- Body editor container (contenteditable): <fill>
- Image-insert control ("+" / toolbar button): <fill>
- Hidden file input for image upload: <fill>
- Caption field on an inserted image block: <fill>

## Text paste mechanism (pick the one that works)
- [ ] clipboard write via context.grant_permissions(["clipboard-write"]) + Ctrl+V
- [ ] dispatch a `paste` event with DataTransfer(text/html)
- Notes on what survived (h2, bold, em): <fill>

## Markers
- Do `[[IMG:...]]` / `[[CAP:...]]` markers survive the paste verbatim? <fill>
- Can the cursor be placed on a marker to replace it? <fill>
- If markers are unreliable -> fall back to per-block typing (variant A). Decision: <fill>

## Image upload
- After set_input_files on the file input, does a real image block appear? <fill>
- Where/how is the caption entered for that block? <fill>
```

**Step 2: Write the discovery script**

```python
# src/discover_vc.py
"""Open VC in a persistent, visible browser and pause for manual inspection.

Usage: python -m src.discover_vc
Log in by hand if prompted, navigate to the new-entry page, then use the
opened DevTools / page to record selectors into
experiments/03-vc-editor/notes.md. Press Enter in the terminal to close.
"""
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".vc-profile"
VC_URL = "https://vc.ru/"  # confirm exact new-entry URL during discovery


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"]
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(VC_URL)
        input("Inspect VC, record selectors. Press Enter here to close...\n")
        ctx.close()


if __name__ == "__main__":
    main()
```

**Step 3: Run it and inspect WITH the user**

Run: `python -m src.discover_vc`
Expected: a visible Chromium opens on VC. Log in once (cookies persist in `.vc-profile/`). Fill every `<fill>` in `notes.md`. Confirm the paste mechanism on a small HTML snippet (h2 + paragraph + bold + em) and one `image5.png` upload.

**Step 4: Commit the recorded findings**

```bash
git add src/discover_vc.py experiments/03-vc-editor/notes.md
git commit -m "experiment(03): VC editor discovery — selectors + paste mechanism"
```

---

## Task 10: VC adapter (manual validation loop — NOT TDD)

> Browser automation is verified by running it and inspecting the draft, not by unit tests. Use the selectors/mechanism recorded in Task 9. Build incrementally and commit after each working sub-step. The skeleton below uses placeholder selectors marked `# DISCOVERY:` — replace each with the recorded value.

**Files:**
- Create: `src/vc_adapter.py`

**Step 1: Skeleton — launch persistent context, wait for login, open new entry**

```python
# src/vc_adapter.py
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".vc-profile"
NEW_ENTRY_URL = "https://vc.ru/"  # DISCOVERY: exact new-entry URL


def open_editor(page):
    page.goto(NEW_ENTRY_URL)
    # DISCOVERY: if logged-out selector is visible, pause for manual login
    login_marker = "<fill>"  # DISCOVERY
    if page.locator(login_marker).count() > 0:
        input("Log in to VC in the browser, then press Enter here...\n")
    page.goto(NEW_ENTRY_URL)


def run(slug_dir: str):
    slug = Path(slug_dir)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"]
        )
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        open_editor(page)
        input("Editor open. Press Enter to close (build next steps incrementally)...\n")
        ctx.close()
```

Run: `python -c "from src.vc_adapter import run; run('example')"`
Expected: visible browser opens the new-entry editor (after manual login on first run). Commit:
```bash
git add src/vc_adapter.py
git commit -m "feat(vc): launch persistent context and open the editor"
```

**Step 2: Set the title.** Add a `set_title(page, title)` using the recorded title selector; call it with `doc.title`. Verify the title appears. Commit `feat(vc): set entry title`.

**Step 3: Paste the body.** Add `paste_body(page, body_html)` using the mechanism chosen in Task 9 (clipboard+Ctrl+V, or a dispatched `paste` event with `DataTransfer`). Feed `emit_body(parse(index_html))`. Verify headings/paragraphs/bold/em land and the `[[IMG:...]]`/`[[CAP:...]]` markers are visible. Commit `feat(vc): paste text body with markers`.

**Step 4: Replace image markers with uploaded images.** For each `Image` block in order: locate its `[[IMG:file]]` marker, place the cursor there, trigger the editor's image-insert control, and `set_input_files` the hidden file input with `slug/images/<file>`. Wait for the real image block, then remove the marker text. Commit `feat(vc): upload images into their markers`.

**Step 5: Fill captions.** For each `[[CAP:text]]` marker (or image with a caption in IR), enter the text into the inserted image's caption field, then remove the marker. Commit `feat(vc): attach image captions`.

**Step 6: Confirm draft + stop.** Wait for VC's autosave/draft indicator (recorded in Task 9); print the draft URL; leave the window open. Commit `feat(vc): confirm saved draft and stop`.

**Validation loop (per design):** run on `example/` (or a real `in/<slug>/`), inspect the draft in VC, change ONE thing at a time, re-run, repeat until the draft is clean. Record deltas in `experiments/03-vc-editor/notes.md`.

**Fallback:** if markers prove unreliable in Step 3–4 (per Task 9 finding), switch `paste_body` to per-block typing (variant A): type each paragraph and press Enter, set headings via the editor control, and insert images at the current cursor instead of via markers. Keep the same image-upload code from Step 4.

---

## Task 11: Entry point

**Files:**
- Create: `run_vc.py`

**Step 1: Write the entry point**

```python
# run_vc.py
"""Usage: python run_vc.py in/<slug>

Parses the GDoc export in the given folder and drives the VC editor to a
saved draft. The browser stays open for manual review and publishing.
"""
import sys
from pathlib import Path
from src.parser import parse
from src.emit_html import emit_body
from src import vc_adapter


def main():
    if len(sys.argv) != 2:
        print("Usage: python run_vc.py in/<slug>")
        raise SystemExit(2)
    slug_dir = Path(sys.argv[1])
    index = slug_dir / "index.html"
    if not index.exists():
        print(f"Not found: {index}")
        raise SystemExit(1)

    doc = parse(index.read_text(encoding="utf-8"))
    images = sorted(p.name for p in (slug_dir / "images").glob("*.png"))
    referenced = [b.file for b in doc.blocks if hasattr(b, "file")]
    missing = [f for f in referenced if f not in images]
    if missing:
        print(f"WARNING: referenced images not found on disk: {missing}")

    body_html = emit_body(doc)
    print(f"Parsed: title={doc.title!r}, blocks={len(doc.blocks)}, images={len(referenced)}")
    vc_adapter.run_document(str(slug_dir), doc, body_html)


if __name__ == "__main__":
    main()
```

**Step 2: Align the adapter entry**

Refactor `vc_adapter.run` into `run_document(slug_dir, doc, body_html)` so `run_vc.py` passes the already-parsed document and emitted HTML (DRY — parsing lives in one place).

**Step 3: Smoke test the parse/emit path without the browser**

Run: `python -c "from pathlib import Path; from src.parser import parse; from src.emit_html import emit_body; d=parse(Path('example/index.html').read_text(encoding='utf-8')); print(emit_body(d)[:500])"`
Expected: clean HTML with `<h2>`, `<p>`, `<strong>`/`<em>`, and `[[IMG:...]]` markers.

**Step 4: Full run against the example**

Run: `python run_vc.py example`
Expected: parse summary prints; visible browser opens; draft is built and saved; window stays open.

**Step 5: Commit**

```bash
git add run_vc.py src/vc_adapter.py
git commit -m "feat: run_vc.py entry point wiring parser -> emitter -> VC adapter"
```

---

## Done criteria

- `python -m pytest -q` is green (parser + emitter covered by tests).
- `experiments/03-vc-editor/notes.md` has no remaining `<fill>` placeholders.
- `python run_vc.py example` produces a VC draft whose text, formatting, images, and captions match the source, verified by eye in the validation loop.

## Out of scope (per design)

Lists, tables, code, Google link wrappers, embeds, quotes (yellow highlight); API posting; CLI packaging; other platforms (Dzen/Habr/Smartlab). The IR is shaped to accept them later.

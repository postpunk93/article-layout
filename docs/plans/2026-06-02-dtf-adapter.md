# DTF Adapter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `dtf` platform that lays out a parsed GDoc article as an autosaved draft
in DTF's Osnova/Editor.js editor, never publishing — plus fix the premature stop signal
shared with VC and add a short synthetic `.docx` test fixture.

**Architecture:** DTF (dtf.ru) and VC (vc.ru) run the same Komitet **Osnova** engine
(Editor.js), so `src/dtf_adapter.py` is a copy of the validated `src/vc_adapter.py` with
only the editor URL (and any recon-confirmed diverging selectors) changed. The body is
built by one real clipboard paste, then restore passes re-apply strong/em, convert
paragraphs to native quotes, and replace `[[IMG file]]` markers with native image
uploads. Registered in `src/sessions.py` `PLATFORMS` with standard `open_context` login.

**Tech Stack:** Python, Playwright (sync API, `channel="chrome"`), pytest, python-docx
(1.2.0, already installed). Reuse `src/emit_html.emit_body` and the Editor.js patterns
in `src/vc_adapter.py`.

**Design doc:** `docs/plans/2026-06-02-dtf-adapter-design.md` (read it first — records the
approach decision, the stop-signal bug, and the synthetic-doc plan).

**Profile:** the `default` profile is logged into DTF — use it for every live
verification. The `layout` command reads `in/<slug>/index.html` + `in/<slug>/images/`.

---

## Task 1: Live recon of the DTF editor

Confirm what the design assumes before copying VC. Record findings; they drive Tasks 3–4.

**Files:**
- Create (scratch, deleted in Task 7): `recon_dtf.py`

**Step 1: Write a recon probe**

```python
# recon_dtf.py — scratch; DELETE in Task 7
from playwright.sync_api import sync_playwright
from src import sessions

with sync_playwright() as p:
    ctx, page = sessions.open_context(p, "default", headless=False)
    page.goto("https://dtf.ru/?modal=editor")
    page.wait_for_timeout(4000)
    print("URL:", page.url)
    for sel in [
        'div.editor-tool-input[data-placeholder="Заголовок"]',
        ".codex-editor", ".ce-block", ".ce-toolbar__plus",
        ".editor-tool-input--text-sm",
        ".editor-quote-tool .editor-tool-input--multiline",
    ]:
        print(sel, "->", page.locator(sel).count())
    # Footer save status: dump candidate text near the publish button.
    print("FOOTER:", page.evaluate(
        "() => [...document.querySelectorAll('button, span, div')]"
        ".map(e => (e.innerText||'').trim())"
        ".filter(t => /Сохран|Опубликов/.test(t)).slice(0,10)"))
    input("Type the title, paste a line, watch the footer; press Enter to close...")
    ctx.close()
```

**Step 2: Run it and record findings**

Run: `python recon_dtf.py`
Record, in the design doc's recon section (append a "Recon findings (verified live)"):
- the exact editor URL after load,
- which VC selectors matched (count > 0) and any that differ,
- the footer **save-status** selector/text («Сохранение» → «Сохранено») observed after a paste.

**Step 3: Commit the recorded findings**

```bash
git add docs/plans/2026-06-02-dtf-adapter-design.md
git commit -m "docs(dtf): record live recon findings"
```

No code commit here — `recon_dtf.py` is scratch and stays uncommitted.

---

## Task 2: Synthetic test-document generator

A short, all-cases `.docx` authored to our GDoc conventions. The user opens it in Google
Docs, reviews it, and "Download → HTML" into `in/synthetic/` for the e2e (Task 6).

**Files:**
- Create: `tools/make_test_doc.py`
- Create (generated): `fixtures/synthetic.docx`, `fixtures/img1.png`, `fixtures/img2.png`
- Test: `tests/test_make_test_doc.py`

**Step 1: Write the failing test**

```python
# tests/test_make_test_doc.py
import subprocess, sys
from pathlib import Path
from docx import Document
from docx.enum.text import WD_COLOR_INDEX

OUT = Path("fixtures/synthetic.docx")

def test_generator_produces_doc_with_conventions(tmp_path):
    subprocess.run([sys.executable, "tools/make_test_doc.py"], check=True)
    assert OUT.exists()
    doc = Document(str(OUT))
    styles = [p.style.name for p in doc.paragraphs]
    assert "Heading 1" in styles          # title
    assert "Heading 2" in styles and "Heading 3" in styles
    # at least one run is yellow-highlighted (the quote)
    highlighted = [r for p in doc.paragraphs for r in p.runs
                   if r.font.highlight_color == WD_COLOR_INDEX.YELLOW]
    assert highlighted, "expected a yellow-highlighted quote run"
    # at least one bold and one italic run somewhere
    assert any(r.bold for p in doc.paragraphs for r in p.runs)
    assert any(r.italic for p in doc.paragraphs for r in p.runs)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_make_test_doc.py -v`
Expected: FAIL (`tools/make_test_doc.py` does not exist → CalledProcessError / file missing).

**Step 3: Write the generator**

```python
# tools/make_test_doc.py
"""Generate fixtures/synthetic.docx — a short, all-cases test article authored to our
GDoc conventions. Open it in Google Docs, review, then Download -> HTML into in/synthetic/.

Conventions: Heading 1 = title; Heading 2/3 = headings; yellow highlight = quote;
italic text under an image = caption; bold/italic inline; bulleted + numbered lists.
"""
from pathlib import Path
from docx import Document
from docx.shared import Inches
from docx.enum.text import WD_COLOR_INDEX

FIX = Path("fixtures")


def _tiny_png(path: Path, rgb: bytes):
    # Minimal solid-color PNG via Pillow if present, else a 1x1 raw fallback.
    try:
        from PIL import Image
        Image.new("RGB", (240, 160), rgb).save(path)
    except ImportError:
        # 1x1 transparent PNG (valid, just tiny) — distinct files still upload fine.
        import base64
        path.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="))


def build():
    FIX.mkdir(exist_ok=True)
    img1, img2 = FIX / "img1.png", FIX / "img2.png"
    _tiny_png(img1, (220, 80, 80))
    _tiny_png(img2, (80, 120, 220))

    doc = Document()
    doc.add_heading("Тестовый документ для вёрстки", level=1)

    p = doc.add_paragraph("Обычный абзац со ")
    p.add_run("жирным").bold = True
    p.add_run(" и ")
    p.add_run("курсивным").italic = True
    p.add_run(" словами.")

    doc.add_heading("Подзаголовок второго уровня", level=2)
    doc.add_paragraph("Короткий абзац под H2 для проверки структуры.")

    doc.add_heading("Подзаголовок третьего уровня", level=3)
    doc.add_paragraph("Первый пункт", style="List Bullet")
    b = doc.add_paragraph(style="List Bullet")
    b.add_run("Пункт с ")
    b.add_run("жирным").bold = True
    b.add_run(" и ")
    b.add_run("курсивом").italic = True
    doc.add_paragraph("Третий пункт", style="List Bullet")

    doc.add_paragraph("Первый шаг", style="List Number")
    doc.add_paragraph("Второй шаг", style="List Number")

    q = doc.add_paragraph()
    qr = q.add_run("Это цитата — выделена жёлтым, должна стать нативным блоком цитаты.")
    qr.font.highlight_color = WD_COLOR_INDEX.YELLOW

    doc.add_picture(str(img1), width=Inches(2.5))
    cap1 = doc.add_paragraph()
    cap1.add_run("Подпись к первой картинке").italic = True

    doc.add_picture(str(img2), width=Inches(2.5))
    cap2 = doc.add_paragraph()
    cap2.add_run("Подпись ко второй картинке").italic = True

    doc.add_paragraph("Короткий финальный абзац.")

    out = FIX / "synthetic.docx"
    doc.save(str(out))
    print("wrote", out)


if __name__ == "__main__":
    build()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_make_test_doc.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tools/make_test_doc.py tests/test_make_test_doc.py fixtures/synthetic.docx fixtures/img1.png fixtures/img2.png
git commit -m "feat(test): synthetic .docx fixture generator covering all layout cases"
```

**Step 6: Hand the .docx to the user**

Tell the user: open `fixtures/synthetic.docx` in Google Docs, eyeball it, then
"Файл → Скачать → Веб-страница (.html, .zip)" and unzip into `in/synthetic/`
(so `in/synthetic/index.html` + `in/synthetic/images/` exist). The e2e (Task 6)
runs on that folder. **Pause here until the user confirms `in/synthetic/` is in place.**

---

## Task 3: Copy the VC adapter to `dtf_adapter`

**Files:**
- Create: `src/dtf_adapter.py` (copy of `src/vc_adapter.py`)
- Test: `tests/test_dtf_format_segments.py`

**Step 1: Write the failing test** (mirror `tests/test_vc_format_segments.py`)

```python
# tests/test_dtf_format_segments.py
from src.ir import Run
from src.dtf_adapter import format_segments


def test_no_formatting_returns_empty():
    assert format_segments([Run("plain text", False, False)]) == []


def test_bold_run_offsets():
    runs = [Run("a ", False, False), Run("bold", True, False), Run(" end", False, False)]
    assert format_segments(runs) == [(2, 6, True, False)]


def test_italic_and_bolditalic():
    runs = [Run("x", False, True), Run("y", True, True)]
    assert format_segments(runs) == [(0, 1, False, True), (1, 2, True, True)]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_dtf_format_segments.py -v`
Expected: FAIL with "No module named 'src.dtf_adapter'".

**Step 3: Create `src/dtf_adapter.py`**

Copy `src/vc_adapter.py` verbatim, then change:
- The module docstring's first line to name DTF instead of VC.
- `EDITOR_URL` to the value confirmed in Task 1 (expected `"https://dtf.ru/?modal=editor"`).
- Any selector constant that Task 1 recorded as diverging from VC (expected: none).

Do NOT change anything else in this task (the stop-signal fix is Task 4, applied to both
files together).

```bash
cp src/vc_adapter.py src/dtf_adapter.py
# then edit EDITOR_URL + docstring (+ diverging selectors if any) per Task 1
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_dtf_format_segments.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/dtf_adapter.py tests/test_dtf_format_segments.py
git commit -m "feat(dtf): adapter copied from VC (Osnova/Editor.js), DTF editor URL"
```

---

## Task 4: Fix the stop signal in both VC and DTF

The `id=`-in-URL wait fires after the first paste (before images). Replace it with a wait
for the footer **«Сохранено»** status after the last mutating action. Use the
selector/text confirmed in Task 1.

**Files:**
- Modify: `src/vc_adapter.py` (the step-5 "Confirm the draft saved" block, ~lines 310–315)
- Modify: `src/dtf_adapter.py` (same block)

**Step 1: Add a shared-shape helper to BOTH adapters**

Replace the final `try/except` that waits for `location.href.includes('id=')` with a wait
for the saved status. Use the recon-confirmed text; the form below matches the footer text
case-insensitively and requires it to NOT be the in-progress «Сохранение»:

```python
    # 5. Confirm the draft autosaved. The URL gains id= after the FIRST paste (long
    # before images finish), so it is NOT a reliable "saved" signal — wait for the
    # footer status to settle on «Сохранено» (not «Сохранение») after the last upload.
    try:
        page.wait_for_function(
            """() => {
                const txt = [...document.querySelectorAll('button, span, div')]
                    .map(e => (e.innerText || '').trim())
                    .find(t => /^Сохран(ено|яется|ение)/i.test(t)) || '';
                return /Сохранено/i.test(txt);
            }""",
            timeout=20000,
        )
        log(f"Draft autosaved (status «Сохранено»): {page.url}")
    except Exception:
        log(f"WARNING: did not observe «Сохранено» status; current: {page.url}")
```

If Task 1 found a precise status selector, prefer it over the broad scan (narrow the
querySelectorAll to that selector). Keep the two files identical in this block.

**Step 2: Run the unit suite (no regression in pure helpers)**

Run: `pytest tests/test_vc_format_segments.py tests/test_dtf_format_segments.py -v`
Expected: PASS (this block has no unit coverage; the real check is the e2e in Task 6).

**Step 3: Commit**

```bash
git add src/vc_adapter.py src/dtf_adapter.py
git commit -m "fix(vc,dtf): wait for «Сохранено» footer status, not premature id= in URL"
```

---

## Task 5: Register `dtf` in the platform registry

**Files:**
- Modify: `src/sessions.py` (import + `PLATFORMS`)
- Test: `tests/test_sessions_registry.py`

**Step 1: Write the failing test**

Update `test_registry_has_all_platforms` and `test_known_platforms_helper`, and add a
contract test (mirror `test_lj_registered_with_contract`):

```python
def test_registry_has_all_platforms():
    assert set(sessions.PLATFORMS) == {"vc", "pikabu", "habr", "smartlab", "dzen", "lj", "dtf"}

def test_known_platforms_helper():
    assert sessions.known_platforms() == ["dtf", "dzen", "habr", "lj", "pikabu", "smartlab", "vc"]

def test_dtf_registered_with_contract():
    entry = sessions.PLATFORMS["dtf"]
    assert callable(entry["build_document"])
    assert entry["editor_url"].startswith("http")
    assert entry["alive_marker"]
    # Same Osnova engine as VC; standard CDP login, no manual_login.
    assert "manual_login" not in entry
    assert "dtf" in sessions.known_platforms()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_sessions_registry.py -v`
Expected: FAIL (`KeyError: 'dtf'` / set mismatch).

**Step 3: Register the platform**

In `src/sessions.py`, add `dtf_adapter` to the import line, then add to `PLATFORMS`:

```python
    "dtf": {
        "build_document": dtf_adapter.build_document,
        "editor_url": dtf_adapter.EDITOR_URL,
        # Same Osnova editor as VC; the title field renders only when logged in.
        "alive_marker": dtf_adapter.TITLE_SEL,
    },
```

**Step 4: Run the full unit suite**

Run: `pytest -q`
Expected: PASS (all tests green).

**Step 5: Commit**

```bash
git add src/sessions.py tests/test_sessions_registry.py
git commit -m "feat(dtf): register dtf platform in session registry"
```

---

## Task 6: End-to-end validation (DTF) + VC regression

**Prerequisite:** `in/synthetic/index.html` + `in/synthetic/images/` exist (Task 2, Step 6).

**Step 1: Lay out the synthetic doc on DTF**

Run: `python cli.py layout synthetic default dtf`
Watch the visible browser. Expected:
- title set; body pasted with H2/H3, bulleted + numbered lists, bold/italic;
- the yellow paragraph became a native quote block;
- both images uploaded with their italic captions;
- the run stops at the footer «Сохранено» and never clicks «Опубликовать».

Fix any selector divergence in `src/dtf_adapter.py` only (re-run until clean). If the
caption landed as a separate paragraph rather than the image's native caption, that is a
parser/round-trip issue — record it and resolve per the design's round-trip caveat.

**Step 2: Regression — lay out an existing sample on VC**

Run: `python cli.py layout lists-quotes default vc`
Expected: VC still builds the draft and now stops at «Сохранено» (the fixed signal),
never publishing.

**Step 3: Commit any selector fixes made during e2e**

```bash
git add src/dtf_adapter.py
git commit -m "fix(dtf): e2e selector adjustments from live validation"
```

(Skip if no changes were needed.)

---

## Task 7: Cleanup, docs, and merge

**Step 1: Delete scratch recon files**

```bash
rm -f recon_dtf.py
git status   # confirm nothing scratch is staged
```

**Step 2: Update memory + design doc status**

- Mark the design doc `Status:` as "implemented, validated e2e".
- Add a memory file `project_dtf_adapter.md` (and an index line in `MEMORY.md`) noting:
  DTF = VC copy on Osnova/Editor.js; branch `feat/dtf-adapter`; the shared stop-signal
  fix («Сохранено», not `id=`); the synthetic `.docx` fixture under `fixtures/` +
  `tools/make_test_doc.py`. Link `[[project_vc_paste_layout]]`.

**Step 3: Final commit**

```bash
git add docs/plans/2026-06-02-dtf-adapter-design.md
git commit -m "docs(dtf): mark design implemented; e2e-validated DTF adapter"
```

**Step 4: Finish the branch**

Use superpowers:finishing-a-development-branch to merge `feat/dtf-adapter` into `main`.

---

## Notes

- DRY: DTF deliberately duplicates VC (one-file-per-platform convention); the only
  intentional shared edit is the stop-signal block, kept byte-identical in both files.
- YAGNI: no shared `osnova` core, no DTF-only blocks, no publish flow.
- TDD: pure helpers (`format_segments`, the doc generator) are unit-tested; the browser
  paste/upload/stop logic is verified e2e (the project's established pattern).
- Never publish — every path stops at the autosaved draft.

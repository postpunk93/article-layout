# Image Transport Experiment — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Find the simplest way to make images survive a copy-paste from a locally-opened HTML file into a fresh VC.ru article draft.

**Architecture:** No converter code yet. We hand-build minimal HTML files (one heading, two paragraphs, one image) using different image-transport strategies, and have the user paste each into VC. The first strategy that lands the image as a real image block wins and becomes the rule for the future converter.

**Tech Stack:** Hand-written HTML; Python 3 (already on system) for one-line `http.server`; user's Chrome + VC.ru editor for validation.

**Design doc:** `docs/plans/2026-05-25-article-layout-design.md` — read first if context is missing.

**Important:** these experiments produce knowledge, not code. The "test" is a human visually verifying the paste in VC and writing findings into `notes.md`. Stop at the first experiment that succeeds; later experiments are only run if earlier ones fail.

---

### Task 0: Initialize project skeleton

**Files:**
- Create: `C:\Projects\article-layout\.gitignore`
- Create: `C:\Projects\article-layout\experiments\` (directory)
- Create: `C:\Projects\article-layout\in\.gitkeep`
- Create: `C:\Projects\article-layout\out\.gitkeep`

**Step 1: Create folder structure**

Run from `C:\Projects\article-layout`:

```powershell
New-Item -ItemType Directory -Force experiments, in, out, src | Out-Null
```

**Step 2: Write `.gitignore`**

```
out/
in/*/
!in/.gitkeep
node_modules/
__pycache__/
*.pyc
.venv/
```

**Step 3: Optional — `git init`**

Skip if user prefers not to use git. Otherwise:

```powershell
git init
git add .gitignore example docs
git commit -m "chore: initial project skeleton with example article and design doc"
```

**Step 4: Verify**

Run: `Get-ChildItem -Force` from project root.
Expected: see `example/`, `docs/`, `experiments/`, `in/`, `out/`, `src/`, `.gitignore`.

---

### Task 1: Experiment 01 — Data URI

The hypothesis: VC's paste handler accepts `<img src="data:image/png;base64,…">` inline.

**Files:**
- Create: `experiments\01-data-uri\test.html`
- Create: `experiments\01-data-uri\notes.md`

**Step 1: Generate the HTML with embedded image**

Write a tiny Python script `experiments\01-data-uri\build.py` that reads `example\images\image5.png`, base64-encodes it, and emits `test.html`:

```python
import base64
from pathlib import Path

img = Path(__file__).resolve().parents[2] / "example" / "images" / "image5.png"
b64 = base64.b64encode(img.read_bytes()).decode("ascii")

html = f"""<!doctype html>
<html lang="ru">
<head><meta charset="utf-8"><title>experiment-01-data-uri</title></head>
<body>
<h1>Эксперимент 01 — data URI</h1>
<p>Это первый абзац. Дальше будет картинка с подписью.</p>
<figure>
  <img src="data:image/png;base64,{b64}" alt="">
  <figcaption>Это я)</figcaption>
</figure>
<p>Это абзац после картинки.</p>
</body>
</html>
"""

Path(__file__).with_name("test.html").write_text(html, encoding="utf-8")
print(f"wrote test.html, image bytes: {len(b64)} base64 chars")
```

**Step 2: Run the script**

Run from project root:

```powershell
python experiments\01-data-uri\build.py
```

Expected: prints `wrote test.html, image bytes: <number>`. `test.html` exists and is ~50–200 KB.

**Step 3: Pre-flight the file in browser**

User opens `test.html` in Chrome (double-click). Verify visually: heading appears, image renders, caption "Это я)" is under it, two surrounding paragraphs visible. If image does not render in Chrome itself, abort — the file is broken and the experiment is invalid.

**Step 4: Paste test into VC**

User:
1. In Chrome on `test.html`: `Ctrl+A` then `Ctrl+C`.
2. Open `https://vc.ru/new` (create a new article draft).
3. Click into the editor body and `Ctrl+V`.
4. Take a screenshot.

**Step 5: Record findings**

Create `experiments\01-data-uri\notes.md`:

```markdown
# Experiment 01 — Data URI

**Date:** YYYY-MM-DD
**Source:** `experiments/01-data-uri/test.html` (heading + 2 paragraphs + figure with data-URI image + figcaption)

## Result

- Heading: <kept as H? / merged into paragraph / lost>
- Paragraphs: <kept / merged / split>
- Image: <appeared as image block / appeared as broken icon / silently dropped / something else>
- Caption: <attached to image as caption / orphaned paragraph below / lost>

## Screenshot

(attach or describe)

## Verdict

- [ ] PASS — image lands as a real image block. Stop here. Data URI is our strategy.
- [ ] FAIL — proceed to Task 2 (experiment 02).
```

**Step 6: Commit (if using git)**

```powershell
git add experiments\01-data-uri
git commit -m "experiment(01): data URI image transport — result: <PASS|FAIL>"
```

**Stop condition:** if PASS — skip Tasks 2–4, jump to Task 5 (close-out).

---

### Task 2: Experiment 02 — Local HTTP server

Run **only if Task 1 failed.** Hypothesis: VC behaves differently when the source page is served over HTTP (`http://localhost:8000/`) instead of `file://`.

**Files:**
- Create: `experiments\02-localhost\test.html`
- Create: `experiments\02-localhost\images\image5.png` (copy of `example\images\image5.png`)
- Create: `experiments\02-localhost\notes.md`

**Step 1: Set up folder**

```powershell
New-Item -ItemType Directory -Force experiments\02-localhost\images | Out-Null
Copy-Item example\images\image5.png experiments\02-localhost\images\
```

**Step 2: Write `test.html` with relative image path**

`experiments\02-localhost\test.html`:

```html
<!doctype html>
<html lang="ru">
<head><meta charset="utf-8"><title>experiment-02-localhost</title></head>
<body>
<h1>Эксперимент 02 — localhost</h1>
<p>Это первый абзац. Дальше будет картинка с подписью.</p>
<figure>
  <img src="images/image5.png" alt="">
  <figcaption>Это я)</figcaption>
</figure>
<p>Это абзац после картинки.</p>
</body>
</html>
```

**Step 3: Start a local HTTP server**

In a separate PowerShell window, from `C:\Projects\article-layout\experiments\02-localhost`:

```powershell
python -m http.server 8000
```

Leave running. Verify by opening `http://localhost:8000/test.html` in Chrome — image must render.

**Step 4: Paste test**

Same procedure as Task 1 Step 4, but copying from the `http://localhost:8000/test.html` tab.

**Step 5: Record findings**

Create `experiments\02-localhost\notes.md` mirroring the schema from Task 1. Add a verdict.

**Step 6: Stop server and commit**

`Ctrl+C` in the server window.

```powershell
git add experiments\02-localhost
git commit -m "experiment(02): localhost-served image transport — result: <PASS|FAIL>"
```

**Stop condition:** PASS → skip Tasks 3–4, jump to Task 5.

---

### Task 3: Experiment 03 — Publicly hosted image

Run **only if Tasks 1 and 2 failed.** Hypothesis: VC's editor only accepts images it can fetch from a public `https://` URL (likely re-uploading them to its own CDN on save).

**Files:**
- Create: `experiments\03-public-url\test.html`
- Create: `experiments\03-public-url\notes.md`

**Step 1: Host the image publicly**

Pick the simplest available option **at the moment of execution** — pause and ask the user which host they have at hand:

- A public Google Drive link (requires "anyone with link can view")
- An imgbb / Imgur / Catbox quick upload
- A GitHub gist with the image attached
- The user's existing CDN, if any

Record the absolute URL.

**Step 2: Write `test.html`**

Same structure as Task 2 Step 2, but `<img src="<absolute https URL>">`.

**Step 3: Paste test**

Open `test.html` locally in Chrome, copy all, paste into a fresh VC draft, screenshot.

**Step 4: Record findings**

Create `experiments\03-public-url\notes.md`. **Pay special attention** to: did VC fetch and rehost the image (good — article will survive the source going down), or did it keep the external URL (fragile — risks 404 later)?

**Step 5: Commit**

```powershell
git add experiments\03-public-url
git commit -m "experiment(03): public URL image transport — result: <PASS|FAIL>"
```

**Stop condition:** PASS → jump to Task 5.

---

### Task 4: Experiment 04 — Structure-only fallback

Run **only if Tasks 1–3 all failed.** This is the safety net: paste delivers the text structure, then the user drags image files into the editor manually.

**Files:**
- Create: `experiments\04-placeholder\test.html`
- Create: `experiments\04-placeholder\notes.md`

**Step 1: Write `test.html` with image placeholders**

```html
<!doctype html>
<html lang="ru">
<head><meta charset="utf-8"><title>experiment-04-placeholder</title></head>
<body>
<h1>Эксперимент 04 — placeholder</h1>
<p>Это первый абзац. Дальше будет картинка с подписью.</p>
<p>[IMAGE-1: image5.png — Это я)]</p>
<p>Это абзац после картинки.</p>
</body>
</html>
```

**Step 2: Paste test**

User opens, copies all, pastes into a fresh VC draft. Then drags `example\images\image5.png` from File Explorer onto the placeholder line in the editor.

**Step 3: Record findings**

Create `experiments\04-placeholder\notes.md`. Note how many seconds the manual drag adds per image, and whether VC inserts the image **at** the placeholder or appends it at the end of the article.

**Step 4: Commit**

```powershell
git add experiments\04-placeholder
git commit -m "experiment(04): placeholder + manual drag — result: <USABLE|UNUSABLE>"
```

---

### Task 5: Close out Phase 1a

**Files:**
- Modify: `docs\plans\2026-05-25-article-layout-design.md` (append a "Phase 1a — resolved" section)
- Modify: `C:\Users\Alex\.claude\projects\C--Projects-article-layout\memory\project_article_layout.md` (record the winning strategy as a project memory)

**Step 1: Append outcome to design doc**

Append a section to `2026-05-25-article-layout-design.md`:

```markdown
## Phase 1a outcome (resolved YYYY-MM-DD)

**Winning transport:** <data URI | localhost | public URL | placeholder + drag>

**Why:** <one sentence — what the experiments showed>

**Consequence for Phase 1b converter:** <what the converter must do for images>

**Discarded options:**
- <option> — <why it failed>
```

**Step 2: Update project memory**

Add a paragraph to `project_article_layout.md` under a new heading `**Image transport (resolved 2026-05-25):**` so the decision is recalled in future sessions without re-reading the design doc.

**Step 3: Commit**

```powershell
git add docs\plans\2026-05-25-article-layout-design.md
git commit -m "docs: record Phase 1a outcome — image transport = <winner>"
```

**Step 4: Hand off**

Tell the user: Phase 1a is closed. The next step is to write a new plan (`docs/plans/YYYY-MM-DD-vc-converter.md`) for Phase 1b: building the GDoc-to-VC converter using the winning image transport. Do **not** start Phase 1b in the same plan — it's a separate decision cycle.

---

## Notes for the executor

- **One experiment at a time.** Do not run 01 and 02 in parallel. Each costs a few minutes; the value is the per-step learning.
- **The user is the test runner.** Every "Step: Paste into VC" is a manual checkpoint. Wait for their `notes.md` entry before proceeding.
- **Don't optimize the HTML.** No CSS, no extra wrapping, no fancy structure. The point is to isolate the image-transport variable; everything else must be identical across experiments so we know what changed.
- **One image, one caption, two paragraphs, one heading.** That's it. Adding lists/quotes/code here would muddy the result.
- **If VC's UI changes** (different button to create a draft, different paste handler), record that in the experiment's `notes.md` and continue.

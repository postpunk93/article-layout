# Dzen Adapter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Dzen (Яндекс.Дзен) article-editor adapter that lays out a parsed Document into an autosaved Dzen draft, the 5th platform on the shared `parser → IR → adapter` architecture.

**Architecture:** Dzen's editor is Draft.js. The whole body goes in with ONE real clipboard paste of clean `emit_body` HTML — headings, paragraphs, bold/italic, quotes (real `<blockquote>` → native quote block) and lists all survive natively. Only images need a post-paste pass: each `[[IMG:file]]` marker is replaced by a native upload (hidden `input[type=file]`) with the caption typed into the block's `<figcaption>`. Stop at autosave; never publish. Unlike the other adapters, Dzen CANNOT use `sessions.open_context` (launch_persistent_context): the master Yandex SSO cookie is session-scoped and dropped on Chrome close, so a reopened CDP browser bounces to passport login. Instead we launch a real Chrome with a remote-debugging port (no automation flags — Yandex anti-bot accepts it) and `connect_over_cdp` to that SAME live process, never closing it.

**Tech Stack:** Python, Playwright (sync), pytest. Reuses `src/emit_html.emit_body`, `src/ir`, `src/sessions`. Full discovery + verified selectors: `docs/plans/2026-05-31-dzen-adapter-design.md`.

---

## Conventions (read before starting)
- Adapters' browser logic is validated **live end-to-end**, not unit-tested (see existing
  vc/habr/smartlab adapters — they have no browser unit tests). Only **pure helpers** and the
  **registry** get pytest tests. Follow that split here.
- Mirror `src/smartlab_adapter.py` and `src/vc_adapter.py` for style: module docstring explaining
  the strategy, constants for selectors, small helpers, `build_document(page, doc, images_dir, log=print)`.
- Verified selectors live in the design doc — copy them exactly.
- Run tests with `python -m pytest`. Commit after each green step.

---

### Task 1: Register Dzen in the platform registry (TDD)

**Files:**
- Modify: `tests/test_sessions_registry.py`
- Modify: `src/sessions.py:105-136` (PLATFORMS) and import line `:15`
- Create (stub): `src/dzen_adapter.py`

**Step 1: Update the registry tests to expect dzen**

In `tests/test_sessions_registry.py`, change the set in `test_registry_has_all_platforms` to
include `"dzen"`, change `test_known_platforms_helper` expected list to
`["dzen", "habr", "pikabu", "smartlab", "vc"]`, and add a contract test:

```python
def test_dzen_registered_with_contract():
    entry = sessions.PLATFORMS["dzen"]
    assert callable(entry["build_document"])
    assert entry["editor_url"].startswith("http")
    assert entry["alive_marker"]
    assert entry["cdp_attach"] is True          # dzen attaches to a live Chrome
    assert "dzen" in sessions.known_platforms()
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sessions_registry.py -v`
Expected: FAIL — `KeyError: 'dzen'` / module `dzen_adapter` not importable.

**Step 3: Create the adapter stub with constants**

Create `src/dzen_adapter.py` with the module docstring (summarize the design doc) and just the
constants + a stub `build_document` for now:

```python
"""Drive Yandex Dzen's article editor (Draft.js) to build an autosaved draft.

See docs/plans/2026-05-31-dzen-adapter-design.md. Dzen attaches to a LIVE Chrome
via connect_over_cdp (the master Yandex SSO cookie is session-scoped, so the
Habr "login then reopen profile" scheme bounces to passport). One real clipboard
paste carries headings/paragraphs/bold/italic/quotes/lists natively; only images
need a native-upload pass; stop at autosave, never publish.
"""
from pathlib import Path

# Studio dashboard; /profile/editor/create redirects here when logged in.
STUDIO_URL = "https://dzen.ru/profile/editor/create"
DEBUG_PORT = 9222

ADD_PUBLICATION_SEL = '[data-testid="add-publication-button"]'   # the "+" in the studio header
BODY_SEL = '.public-DraftEditor-content[spellcheck="true"]'      # body contenteditable (title is spellcheck=false)
TITLE_SEL = '.public-DraftEditor-content[spellcheck="false"]'    # title contenteditable
STATUS_SEL = '[class*="editor-header__status"]'                  # autosave indicator
SIDE_BUTTON_SEL = '[class*="side-button__sideButton"]'           # reveal-on-hover image "+"
IMAGE_FILE_INPUT_SEL = 'input[type=file][class*="image-popup__file"]'
FIGCAPTION_SEL = 'figure.zen-editor-block-image figcaption'
# Logged-in marker: the studio "+" only renders for an authenticated user.
ALIVE_SEL = ADD_PUBLICATION_SEL


def build_document(page, doc, images_dir, log=print):
    raise NotImplementedError  # filled in by later tasks
```

**Step 4: Register in `src/sessions.py`**

Add `dzen_adapter` to the import on line 15, then add to `PLATFORMS`:

```python
    "dzen": {
        "build_document": dzen_adapter.build_document,
        "editor_url": dzen_adapter.STUDIO_URL,
        "alive_marker": dzen_adapter.ALIVE_SEL,
        # Dzen attaches to a live Chrome over CDP (see adapter docstring); it does
        # NOT use open_context. cli.py branches on this flag.
        "cdp_attach": True,
        "debug_port": dzen_adapter.DEBUG_PORT,
        "manual_login": True,
        "login_url": dzen_adapter.STUDIO_URL,
    },
```

**Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_sessions_registry.py -v`
Expected: PASS.

Also run the existing contract test guard:
Run: `python -m pytest tests/test_sessions_registry.py::test_each_platform_entry_is_complete -v`
Expected: PASS (dzen has build_document/editor_url/alive_marker).

**Step 6: Commit**

```bash
git add tests/test_sessions_registry.py src/sessions.py src/dzen_adapter.py
git commit -m "feat(dzen): register dzen adapter in PLATFORMS (stub)"
```

---

### Task 2: Body-HTML helper (TDD)

The body is generated by `emit_body` with Dzen-specific flags: real `<blockquote>` (Dzen converts
it to a native quote block) and image MARKERS (`[[IMG:file]]`) since data-URIs error in Dzen.
Wrap it in a named helper so the flag choice is explicit and testable.

**Files:**
- Create: `tests/test_dzen_adapter.py`
- Modify: `src/dzen_adapter.py`

**Step 1: Write the failing test**

```python
# tests/test_dzen_adapter.py
from src import dzen_adapter
from src.ir import Document, Paragraph, Quote, Image, Run


def test_body_html_emits_real_blockquote_and_img_markers():
    doc = Document(title="T", blocks=[
        Paragraph(runs=[Run("hello")]),
        Quote(runs=[Run("quoted")]),
        Image(file="image1.png", caption=[Run("cap")]),
    ])
    html = dzen_adapter.body_html(doc)
    assert "<blockquote>quoted</blockquote>" in html   # native quote on paste
    assert "[[IMG:image1.png]]" in html                # image marker, replaced by upload
    assert "data:image" not in html                    # never a data-URI (Dzen errors on it)
    assert "[[CAP:" not in html                         # captions set natively, no marker
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dzen_adapter.py -v`
Expected: FAIL — `AttributeError: module 'src.dzen_adapter' has no attribute 'body_html'`.

**Step 3: Implement `body_html`**

Add to `src/dzen_adapter.py`:

```python
from src.emit_html import emit_body


def body_html(doc):
    """Clean body HTML for the paste: real <blockquote> (Dzen makes a native quote
    block), images as [[IMG:file]] markers (data-URIs error in Dzen), captions set
    natively (no marker)."""
    return emit_body(doc, caption_marker=False, quote_as_paragraph=False, img_sep=":")
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dzen_adapter.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_dzen_adapter.py src/dzen_adapter.py
git commit -m "feat(dzen): body_html helper (real blockquote + image markers)"
```

---

### Task 3: CDP-attach run mode in sessions.py (TDD for the pure parts)

Dzen needs to launch a real Chrome with a debug port and connect over CDP. Add two helpers.

**Files:**
- Modify: `src/sessions.py`
- Create/Modify: `tests/test_sessions_cdp.py`

**Step 1: Write the failing test (URL builder is the pure, testable part)**

```python
# tests/test_sessions_cdp.py
from src import sessions


def test_cdp_endpoint_url():
    assert sessions.cdp_endpoint(9222) == "http://localhost:9222"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sessions_cdp.py -v`
Expected: FAIL — `AttributeError: ... 'cdp_endpoint'`.

**Step 3: Implement the helpers**

Add to `src/sessions.py`:

```python
def cdp_endpoint(port: int) -> str:
    return f"http://localhost:{port}"


def launch_debug_chrome(client: str, platform: str, url: str, port: int,
                        root: Path = PROFILES_ROOT):
    """Launch the user's real Chrome on the profile with a remote-debugging port and
    NO automation flags. Yandex anti-bot rejects CDP-automation-launched Chrome but
    accepts this; Playwright then connect_over_cdp's to it. Returns the Popen — the
    caller MUST keep it alive for the whole layout run (closing drops the session)."""
    exe = chrome_executable()
    if not exe:
        raise RuntimeError("Chrome not found — install Chrome to use Dzen.")
    pdir = profile_dir(client, platform, root)
    pdir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen([
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={pdir.resolve()}",
        url,
    ])
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sessions_cdp.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_sessions_cdp.py src/sessions.py
git commit -m "feat(dzen): cdp_endpoint + launch_debug_chrome helpers"
```

---

### Task 4: Adapter — open a fresh article editor

Implement the navigation: studio → "+" → "Написать статью" → editor body ready.

**Files:**
- Modify: `src/dzen_adapter.py`

**Step 1: Implement `_open_editor`**

```python
import time


def _open_editor(page, log):
    """From a logged-in live session, open a fresh article editor and return when the
    body contenteditable is present."""
    if "/edit" in page.url:
        try:
            page.wait_for_selector(BODY_SEL, timeout=4000)
            return
        except Exception:  # noqa: BLE001
            pass
    log("Opening Dzen studio…")
    page.goto(STUDIO_URL, wait_until="domcontentloaded")
    page.wait_for_selector(ADD_PUBLICATION_SEL, timeout=30000)  # logged-in marker
    page.locator(ADD_PUBLICATION_SEL).first.click()
    page.wait_for_timeout(800)
    for item in ["text=Написать статью", "text=Статья"]:
        loc = page.locator(item)
        if loc.count():
            loc.first.click()
            break
    page.wait_for_selector(BODY_SEL, timeout=20000)
    log(f"Article editor: {page.url}")
```

**Step 2: Smoke-check import**

Run: `python -c "import src.dzen_adapter"`
Expected: no error.

**Step 3: Commit**

```bash
git add src/dzen_adapter.py
git commit -m "feat(dzen): open fresh article editor via studio + button"
```

---

### Task 5: Adapter — title + body paste

**Files:**
- Modify: `src/dzen_adapter.py`

**Step 1: Implement clipboard + paste helpers**

Reuse the VC clipboard pattern (real Clipboard API write + real Ctrl+V — DraftJS processes a
real paste like a manual one):

```python
def _set_clipboard(page, html):
    page.evaluate(
        """async (html) => {
            const plain = html.replace(/<[^>]+>/g, '');
            await navigator.clipboard.write([new ClipboardItem({
                'text/html': new Blob([html], {type: 'text/html'}),
                'text/plain': new Blob([plain], {type: 'text/plain'}),
            })]);
        }""",
        html,
    )


def _set_title_and_body(page, doc, log):
    log(f"Title: {doc.title!r}")
    page.click(TITLE_SEL)
    page.keyboard.type(doc.title)
    # Move into the body and paste the whole structure with one real Ctrl+V.
    html = body_html(doc)
    _set_clipboard(page, html)
    page.click(BODY_SEL)
    page.keyboard.press("Control+V")
    page.wait_for_timeout(1500)
    log("Body pasted.")
```

**Step 2: Smoke-check import**

Run: `python -c "import src.dzen_adapter"`
Expected: no error.

**Step 3: Commit**

```bash
git add src/dzen_adapter.py
git commit -m "feat(dzen): set title and paste body via real clipboard"
```

---

### Task 6: Adapter — native image upload pass

Each `[[IMG:file]]` marker paragraph is replaced by a native upload + figcaption. Discovery proved:
focus an empty block, reveal the side "+" by hovering the block's left gutter, click it (opens an
image popup with a hidden `input[type=file]`), `set_input_files`, wait for the
`avatars.dzeninfra.ru` CDN src, then type the caption into the figcaption.

**Files:**
- Modify: `src/dzen_adapter.py`

**Step 1: Implement `_replace_marker_with_image`**

```python
def _replace_marker_with_image(page, block, path, log):
    needle = f"[[IMG:{block.file}]]"
    # Find and focus the marker block, then clear its text so the upload lands in place.
    idx = page.evaluate(
        """(needle) => {
            const bs = [...document.querySelectorAll('[data-editor="ZenDraftEditor"][data-block="true"]')];
            return bs.findIndex(el => (el.innerText || '').includes(needle));
        }""",
        needle,
    )
    if idx < 0:
        log(f"  marker {needle} not found — skipping")
        return
    block_loc = page.locator('[data-editor="ZenDraftEditor"][data-block="true"]').nth(idx)
    block_loc.scroll_into_view_if_needed()
    block_loc.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    # Reveal the side "+" by hovering the block's left gutter, then click it.
    box = block_loc.bounding_box()
    page.mouse.move(box["x"] + 10, box["y"] + box["height"] / 2)
    page.wait_for_selector(SIDE_BUTTON_SEL, timeout=4000)
    n_before = page.evaluate("() => document.querySelectorAll('figure.zen-editor-block-image img').length")
    page.locator(SIDE_BUTTON_SEL).first.click()
    # The side button opens an image popup carrying a hidden file input.
    page.wait_for_selector(IMAGE_FILE_INPUT_SEL, timeout=8000)
    page.locator(IMAGE_FILE_INPUT_SEL).first.set_input_files(str(path))
    # Wait for the uploaded image to get a real CDN src (avatars.dzeninfra.ru).
    page.wait_for_function(
        """(n) => {
            const imgs = document.querySelectorAll('figure.zen-editor-block-image img');
            if (imgs.length <= n) return false;
            const last = imgs[imgs.length - 1];
            return last.complete && last.naturalWidth > 0 && /^https?:/.test(last.currentSrc || last.src || '');
        }""",
        arg=n_before,
        timeout=60000,
    )
    log(f"  image: {block.file} caption={'yes' if block.caption else 'no'}")
    if block.caption:
        cap_loc = page.locator(FIGCAPTION_SEL).last
        cap_loc.click()
        page.keyboard.type("".join(r.text for r in block.caption))
    time.sleep(0.3)
```

**Step 2: Smoke-check import**

Run: `python -c "import src.dzen_adapter"`
Expected: no error.

**Step 3: Commit**

```bash
git add src/dzen_adapter.py
git commit -m "feat(dzen): native image upload pass (side + -> file input -> figcaption)"
```

---

### Task 7: Adapter — assemble build_document + stop at autosave

**Files:**
- Modify: `src/dzen_adapter.py`

**Step 1: Replace the stub `build_document`**

```python
from src.ir import Image


def build_document(page, doc, images_dir, log=print):
    images_dir = Path(images_dir)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])

    _open_editor(page, log)
    _set_title_and_body(page, doc, log)

    images = [b for b in doc.blocks if isinstance(b, Image)]
    log(f"Uploading {len(images)} image(s)…")
    for block in images:
        path = images_dir / block.file
        if not path.exists():
            log(f"  IMAGE MISSING ON DISK: {path} — leaving marker [[IMG:{block.file}]]")
            continue
        try:
            _replace_marker_with_image(page, block, path, log)
        except Exception as e:  # noqa: BLE001 — report and continue
            log(f"  image {block.file} failed ({str(e)[:80]}) — marker left in body")

    # Stop at the autosaved draft — NEVER click «Опубликовать».
    try:
        page.wait_for_function(
            """(sel) => {
                const s = document.querySelector(sel);
                return s && /сохранен/i.test(s.innerText || '');
            }""",
            arg=STATUS_SEL,
            timeout=20000,
        )
        log("Draft autosaved.")
    except Exception:  # noqa: BLE001
        log(f"WARNING: did not observe autosave status; draft may still be saving. URL: {page.url}")
```

**Step 2: Run the full pure-test suite**

Run: `python -m pytest tests/ -v`
Expected: PASS (registry, body_html, cdp_endpoint, plus all existing parser/emit tests).

**Step 3: Commit**

```bash
git add src/dzen_adapter.py
git commit -m "feat(dzen): assemble build_document, stop at autosave"
```

---

### Task 8: Wire the CDP-attach run mode into cli.py

The existing `cmd_layout` uses `sessions.open_context`. Dzen needs the live-Chrome + attach path.
Keep it isolated behind the `cdp_attach` flag.

**Files:**
- Modify: `cli.py:71-116` (cmd_layout)

**Step 1: Add a dzen branch in `cmd_layout`**

Inside the `for platform in platforms:` loop, branch when `entry.get("cdp_attach")`:

```python
        if entry.get("cdp_attach"):
            # Dzen: launch a real Chrome (debug port), wait for login, attach over CDP.
            port = entry["debug_port"]
            proc = sessions.launch_debug_chrome(args.client, platform, entry["login_url"], port)
            print(f"Chrome up for {args.client}/{platform}. Log in if prompted; leave it open.")
            try:
                with sync_playwright() as p:
                    # Give Chrome a moment to open the debug port.
                    for _ in range(30):
                        try:
                            browser = p.chromium.connect_over_cdp(sessions.cdp_endpoint(port))
                            break
                        except Exception:
                            time.sleep(1)
                    else:
                        raise RuntimeError("Could not connect to Chrome debug port")
                    # Wait until the studio shows the logged-in marker (user may be logging in).
                    page = next((pg for c in browser.contexts for pg in c.pages), None) or browser.contexts[0].new_page()
                    input("Press Enter once you are logged in to Dzen and ready to lay out...")
                    try:
                        entry["build_document"](page, doc, images_dir)
                        print(f"Done — {platform} draft built. Review and publish manually.")
                    except Exception as e:  # noqa: BLE001
                        failures.append((platform, repr(e)))
                        print(f"FAILED {platform}: {e!r} (window left open)")
                    try:
                        input(f"Press Enter to close {platform} browser...")
                    except EOFError:
                        time.sleep(15)
            finally:
                proc.terminate()
            continue
```

(Place this branch BEFORE the existing `with sync_playwright()` open_context block, and add
`continue` so non-cdp platforms keep the old path. Ensure `failures` is defined before the loop —
it already is.)

**Step 2: Adjust precheck for dzen**

`cmd_layout` calls `orchestrator.precheck(...) → sessions.is_alive` which uses `open_context`.
For dzen that would launch a CDP-automation Chrome and (a) fail anti-bot, (b) collide with the
debug-port launch. Exclude `cdp_attach` platforms from the precheck:

In `cmd_layout`, before precheck, split:
```python
    cdp_platforms = [pf for pf in platforms if sessions.PLATFORMS[pf].get("cdp_attach")]
    std_platforms = [pf for pf in platforms if not sessions.PLATFORMS[pf].get("cdp_attach")]
    ok, dead = orchestrator.precheck(args.client, std_platforms, sessions.is_alive)
```
Keep the all-or-nothing gate for `std_platforms`; dzen verifies its own login interactively
(the Enter prompt). Iterate `platforms` as before for the build loop.

**Step 3: Manual smoke — no-session dry check**

Run: `python cli.py status` (should still work; dzen shows DEAD/needs-login since no live attach).
Expected: prints the table without crashing.

Run: `python -m pytest tests/ -v`
Expected: PASS.

**Step 4: Commit**

```bash
git add cli.py
git commit -m "feat(dzen): cli layout via live-Chrome CDP attach (bypass open_context)"
```

---

### Task 9: Live end-to-end validation (manual, like the other adapters)

This is the real acceptance test — browser parts aren't unit-tested.

**Step 1: Run a real layout against the `lists-quotes` fixture**

Run (in your terminal, interactive login):
```
! python cli.py layout lists-quotes default dzen
```
- A real Chrome opens. Log in to Dzen if prompted; reach a state where the studio loads.
- Press Enter to start layout.

**Step 2: Verify in the editor**
- Title set; body present.
- Headings are real H2/H3; paragraphs keep bold/italic.
- The quote is a native quote block (not a plain paragraph).
- Lists are native ul/ol.
- Every image uploaded (CDN src on `avatars.dzeninfra.ru`, no error state) with its caption in the figcaption.
- Status shows «Все изменения сохранены»; nothing was published.

**Step 3: Fix-forward any selector drift**

If a selector moved (CSS-module hashes can change between Dzen deploys), update the constant in
`src/dzen_adapter.py`, re-run, and note it in the design doc. Commit each fix:
```bash
git add src/dzen_adapter.py
git commit -m "fix(dzen): <what changed> selector"
```

**Step 4: Update memory + design doc to DONE**

- Flip `docs/plans/2026-05-31-dzen-adapter-design.md` status to validated.
- Update `project_dzen_adapter` memory + MEMORY.md line from "IN PROGRESS" to "DONE", noting the
  draft was built end-to-end.

---

### Task 10: Clean up discovery tooling

**Step 1: Remove the throwaway harness**

```bash
git rm discovery_dzen.py
git commit -m "chore(dzen): drop discovery harness (adapter validated)"
```

(`discovery/` dumps are gitignored — delete the folder locally too.)

---

## Done criteria
- `python -m pytest tests/ -v` green.
- `python cli.py layout lists-quotes default dzen` builds a complete autosaved Dzen draft:
  title, body with native headings/quotes/lists, bold/italic, all images uploaded with captions,
  nothing published.
- Memory + design doc marked DONE.

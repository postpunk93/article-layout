# Browser Lifecycle: Keep Windows Open Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `cli.py layout` open every platform in its own Chrome window, leave all windows open at the end, and never close a window on its own (removing the EOF/timeout path that lost Habr drafts).

**Architecture:** A single `sync_playwright()` wraps the whole platform loop instead of one iteration. Each platform opens its own persistent context (its own Chrome window) and is built sequentially; no window is closed during or after the loop. A new pure helper `orchestrator.wait_until_all_closed(contexts, pump)` blocks until the user has closed every window, detected by polling `page.is_closed()` — no `input()`, no `sleep`, no programmatic `ctx.close()`.

**Tech Stack:** Python 3.10, Playwright (sync API, `channel="chrome"`), pytest.

**Design doc:** `docs/plans/2026-06-01-browser-lifecycle-keep-open-design.md`

**Branch:** `feat/browser-keep-open` (already created, design doc already committed).

---

### Task 1: Add `wait_until_all_closed` to orchestrator

A pure, browser-free helper: given a list of `(label, ctx)` where each `ctx` has
`.pages` (each page has `is_closed()`), block until every context has no live
page. Event dispatch is injected as a `pump(page)` callback so the function is
testable with fakes and carries no Playwright import.

**Files:**
- Modify: `src/orchestrator.py`
- Test: `tests/test_orchestrator.py`

**Step 1: Write the failing tests**

Add to `tests/test_orchestrator.py`:

```python
class _FakePage:
    def __init__(self, closed):
        self.closed = closed

    def is_closed(self):
        return self.closed


class _FakeCtx:
    def __init__(self, pages):
        self.pages = pages


def test_wait_returns_immediately_when_all_closed():
    ctx = _FakeCtx([_FakePage(closed=True)])
    pumped = []
    orchestrator.wait_until_all_closed([("vc", ctx)], pump=lambda pg: pumped.append(pg))
    assert pumped == []  # nothing live, so never pumped


def test_wait_blocks_until_user_closes_window():
    page = _FakePage(closed=False)
    ctx = _FakeCtx([page])
    calls = {"n": 0}

    def pump(_pg):
        calls["n"] += 1
        page.closed = True  # user closes the window during the wait

    orchestrator.wait_until_all_closed([("vc", ctx)], pump=pump)
    assert calls["n"] == 1


def test_wait_survives_pump_exception():
    page = _FakePage(closed=False)
    ctx = _FakeCtx([page])
    state = {"first": True}

    def pump(_pg):
        if state["first"]:
            state["first"] = False
            page.closed = True
            raise RuntimeError("target closed")  # window vanished mid-pump

    orchestrator.wait_until_all_closed([("vc", ctx)], pump=pump)  # must return, not raise


def test_wait_treats_errored_context_as_closed():
    class _Boom:
        @property
        def pages(self):
            raise RuntimeError("target closed")

    orchestrator.wait_until_all_closed([("vc", _Boom())], pump=lambda pg: None)
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_orchestrator.py -v -k wait`
Expected: FAIL — `AttributeError: module 'src.orchestrator' has no attribute 'wait_until_all_closed'`

**Step 3: Write minimal implementation**

Add to `src/orchestrator.py`:

```python
def wait_until_all_closed(contexts, pump):
    """Block until the user closes every browser window.

    `contexts` is a list of (label, ctx); each ctx exposes `.pages`, and each
    page exposes `is_closed()`. `pump(page)` yields briefly to dispatch browser
    events (in real use, `page.wait_for_timeout(...)`); it may raise if the page
    just closed — that is swallowed and the context re-evaluated as closed.

    This NEVER closes a window itself; it only waits for the user to do so.
    """
    while True:
        live = []
        for label, ctx in contexts:
            try:
                if any(not pg.is_closed() for pg in ctx.pages):
                    live.append((label, ctx))
            except Exception:  # noqa: BLE001 — a vanished context counts as closed
                pass
        if not live:
            return
        try:
            pump(live[0][1].pages[0])
        except Exception:  # noqa: BLE001 — window closed mid-pump; loop re-checks
            pass
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_orchestrator.py -v -k wait`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add src/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(orchestrator): wait_until_all_closed — block until user closes all windows"
```

---

### Task 2: Refactor `cmd_layout` to keep all windows open

Move `sync_playwright()` to wrap the whole loop, accumulate one context per
platform, build sequentially, leave every window open, and replace the
per-platform `input()` + `EOFError`/`sleep`/`ctx.close()` block with a single
`wait_until_all_closed` call. Print the failure summary and compute the exit
code after the windows close.

**Files:**
- Modify: `cli.py` (function `cmd_layout`, currently lines 71-116)

**Step 1: Replace the build loop**

In `cli.py`, replace the current loop body (from `failures = []` through the
final `return` of `cmd_layout`, lines ~95-116) with:

```python
    failures = []
    contexts = []
    with sync_playwright() as p:
        for platform in platforms:
            entry = sessions.PLATFORMS[platform]
            print(f"--- {args.client}/{platform} ---")
            ctx, page = sessions.open_context(p, args.client, platform, headless=False)
            contexts.append((platform, ctx))
            try:
                entry["build_document"](page, doc, images_dir)
                print(f"Done — {platform} draft built. Review and publish manually.")
            except Exception as e:  # noqa: BLE001 — report and continue to next platform
                failures.append((platform, repr(e)))
                print(f"FAILED {platform}: {e!r} (window left open)")

        print(
            f"\nAll {len(contexts)} window(s) open. Review and publish manually. "
            "Nothing will close on its own — close each window yourself when done "
            "(Ctrl+C also exits)."
        )
        orchestrator.wait_until_all_closed(
            contexts, pump=lambda page: page.wait_for_timeout(500)
        )

    if failures:
        print("Failures: " + ", ".join(f"{p}: {err}" for p, err in failures))
        return 1
    return 0
```

**Step 2: Remove the now-unused `time` import if nothing else uses it**

Check: `time` is still used by `cmd_login` (`time.sleep(120)`) and `_today`
(`time.strftime`). Leave the `import time` line as-is — do NOT remove it.

**Step 3: Verify the file parses and tests still pass**

Run: `python -c "import ast; ast.parse(open('cli.py', encoding='utf-8').read()); print('ok')"`
Expected: `ok`

Run: `python -m pytest -q`
Expected: PASS (all existing tests + the 4 new ones; no regressions)

**Step 4: Commit**

```bash
git add cli.py
git commit -m "refactor(cli): keep all layout windows open; never auto-close (no more lost drafts)"
```

---

### Task 3: Manual end-to-end verification

`cmd_layout` drives real browsers and is not unit-tested, so verify by hand with
a logged-in client. Use a slug that already exists under `in/`.

**Step 1: Confirm a usable slug and a logged-in client**

Run: `python cli.py status`
Pick a client with ≥2 alive platforms (e.g. `vc` + `pikabu`). Confirm `in/<slug>/index.html` exists.

**Step 2: Run layout for two platforms**

Run: `python cli.py layout <slug> <client> vc,pikabu`

Verify:
- Two Chrome windows open and **both stay open** at the same time after build.
- The terminal prints "All 2 window(s) open… Nothing will close on its own".
- Neither window closes by itself; the command keeps running.

**Step 3: Confirm manual close ends the command**

Close both Chrome windows by hand.
Verify: the command returns to the shell prompt within ~1 second (exit code 0 if
no failures). Closing only one window does NOT exit; only after both are closed.

**Step 4: Confirm Ctrl+C still works**

Re-run, then press Ctrl+C while windows are open.
Verify: the command exits (windows tear down — intentional interruption).

**Step 5: Record the result**

No commit needed. If anything misbehaves, use superpowers:systematic-debugging
before changing code.

---

### Task 4: Finish the branch

**Step 1: Re-read the design doc and confirm scope**

Confirm adapters, `sessions.py`, and `login`/`status` were untouched, and the
"never auto-close" + "all windows open" behaviors hold.

**Step 2: Use superpowers:finishing-a-development-branch**

Present merge / PR / cleanup options for `feat/browser-keep-open`.

---

## Notes

- **DRY/YAGNI:** No `--close-on-enter` flag, no detach mode, no per-client shared
  profile — those are explicitly out of scope (the shared-profile/tabs idea is in
  the design doc's Backlog).
- **The pump idiom:** `page.wait_for_timeout(500)` is the real event pump; it is
  injected so the helper stays browser-free and unit-tested. If Playwright raises
  because the page closed mid-wait, the helper swallows it and re-checks.
- **Sequential builds are intentional:** clipboard paste + window focus can't be
  parallelized across platforms.

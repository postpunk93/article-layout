# Unified Profile + One-Window Parallel Layout — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

> **NON-NEGOTIABLE — this project NEVER publishes.** Every adapter stops at a built
> draft (+ autosave where present) and leaves the window open. The "publish" click is
> always a human's. No task in this plan adds a publish action.

**Goal:** Lay out all requested platforms for one client in a single Chrome window (a tab per platform), left open, using one shared profile per client.

**Architecture:** Move from per-platform profiles (`.profiles/<client>/<platform>/`) to one shared profile per client (`.profiles/<client>/`). `layout` opens one visible window, checks liveness per platform in tabs (all-or-nothing), then builds drafts in those same tabs sequentially and leaves the window open. `login <client>` opens one plain Chrome to log into every platform at once; `status` probes all known platforms in one context.

**Tech Stack:** Python 3.11+, Playwright (sync API, `channel="chrome"`), pytest. Windows/PowerShell host.

**Design doc:** `docs/plans/2026-06-01-unified-profile-parallel-layout-design.md`

**Conventions for every task below:**
- Run tests with `python -m pytest <path> -v` from the repo root.
- Commit after each task with the message shown.
- Tasks 1–8 are pure-logic / unit-tested (TDD). Tasks 9–13 are browser glue + the Habr marker; they are verified by **manual end-to-end run** (real Chrome + real logins) because they cannot be unit-tested. Follow @superpowers:verification-before-completion before claiming any browser task done.

---

### Task 1: Record the NEVER-publish rule in the repo

**Files:**
- Modify: `docs/platform-notes.md` (prepend a block at the very top)
- Modify: `cli.py` (docstring of `cmd_layout`)

**Step 1: Prepend to `docs/platform-notes.md`**

Add at the very top of the file:

```markdown
> ## NON-NEGOTIABLE: this project NEVER publishes
>
> Every adapter stops at a built draft (plus the platform's own autosave where it
> exists) and leaves the browser window open. The final "publish"/"submit" action is
> ALWAYS performed by a human. Whatever we change in the pipeline, no publish button is
> ever clicked by this code. If this rule ever changes, the user will say so separately
> and explicitly.

```

**Step 2: Add the rule to `cmd_layout`'s docstring in `cli.py`**

Give `cmd_layout` a docstring (it has none today) whose first lines are:

```python
def cmd_layout(args):
    """Build drafts for one client across platforms in a single browser window.

    NEVER publishes: builds drafts and leaves the window open for the human to
    review and publish manually. No publish action is ever taken here.
    """
```

**Step 3: Commit**

```bash
git add docs/platform-notes.md cli.py
git commit -m "docs: record NEVER-publish rule in platform-notes and cmd_layout"
```

---

### Task 2: `profile_dir(client)` and per-client meta

`profile_dir` drops the `platform` argument; the profile is `.profiles/<client>/`. `meta.json` lives at `.profiles/<client>/meta.json`.

**Files:**
- Modify: `src/sessions.py` (`profile_dir`, `_meta_path`, `read_meta`, `write_meta`)
- Test: `tests/test_sessions_paths.py`, `tests/test_sessions_meta.py`

**Step 1: Rewrite the failing tests**

Replace `tests/test_sessions_paths.py` profile-dir test and `tests/test_sessions_meta.py` calls to use the new `(client)` signature:

In `tests/test_sessions_paths.py` replace `test_profile_dir_builds_client_platform_path` with:

```python
def test_profile_dir_builds_client_path():
    root = Path("/tmp/profiles")
    assert sessions.profile_dir("acme", root=root) == root / "acme"
```

In `tests/test_sessions_meta.py` change every call to drop the platform arg, e.g.:

```python
def test_read_meta_missing_returns_empty_dict(tmp_path):
    assert sessions.read_meta("acme", root=tmp_path) == {}

def test_write_then_read_meta_round_trip(tmp_path):
    sessions.write_meta("acme", {"label": "ACME", "login": "a@b.c"}, root=tmp_path)
    assert sessions.read_meta("acme", root=tmp_path) == {"label": "ACME", "login": "a@b.c"}

def test_write_meta_creates_profile_dir(tmp_path):
    sessions.write_meta("new", {"label": "x"}, root=tmp_path)
    assert (tmp_path / "new" / "meta.json").is_file()

def test_write_meta_merges_with_existing(tmp_path):
    sessions.write_meta("acme", {"label": "ACME"}, root=tmp_path)
    sessions.write_meta("acme", {"last_login_at": "2026-05-29"}, root=tmp_path)
    assert sessions.read_meta("acme", root=tmp_path) == {"label": "ACME", "last_login_at": "2026-05-29"}
```

**Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_sessions_paths.py tests/test_sessions_meta.py -v`
Expected: FAIL (signature mismatch / wrong path).

**Step 3: Implement in `src/sessions.py`**

```python
def profile_dir(client: str, root: Path = PROFILES_ROOT) -> Path:
    return Path(root) / client


def _meta_path(client: str, root: Path = PROFILES_ROOT) -> Path:
    return profile_dir(client, root) / "meta.json"


def read_meta(client: str, root: Path = PROFILES_ROOT) -> dict:
    path = _meta_path(client, root)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_meta(client: str, updates: dict, root: Path = PROFILES_ROOT) -> dict:
    """Merge `updates` into the client's meta.json (creating the dir) and return it."""
    pdir = profile_dir(client, root)
    pdir.mkdir(parents=True, exist_ok=True)
    meta = read_meta(client, root)
    meta.update(updates)
    (pdir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta
```

**Step 4: Run to verify pass**

Run: `python -m pytest tests/test_sessions_paths.py tests/test_sessions_meta.py -v`
Expected: PASS (other tests in these files may still fail — fixed in Task 3; that's ok to leave red until then if isolated, but prefer to also do Task 3 before committing).

**Step 5: Commit** (after Task 3 so the file is green)

---

### Task 3: Drop `list_accounts` (folders are no longer per-platform)

`list_clients` stays (folder names under `.profiles/` are clients). `list_accounts` is removed — "which platforms" is no longer folder-derived; `status` probes `known_platforms()` instead (Task 10).

**Files:**
- Modify: `src/sessions.py` (delete `list_accounts`)
- Test: `tests/test_sessions_paths.py` (delete its two `list_accounts` tests)

**Step 1: Delete the two tests** `test_list_accounts_reads_platform_folders` and `test_list_accounts_empty_for_unknown_client` from `tests/test_sessions_paths.py`. Keep `list_clients` tests but change the fixtures so they don't imply per-platform subdirs:

```python
def test_list_clients_reads_folder_names(tmp_path):
    (tmp_path / "acme").mkdir()
    (tmp_path / "beta").mkdir()
    assert sessions.list_clients(root=tmp_path) == ["acme", "beta"]
```

**Step 2: Delete `list_accounts` from `src/sessions.py`.**

**Step 3: Run the sessions path/meta tests**

Run: `python -m pytest tests/test_sessions_paths.py tests/test_sessions_meta.py -v`
Expected: PASS.

**Step 4: Commit**

```bash
git add src/sessions.py tests/test_sessions_paths.py tests/test_sessions_meta.py
git commit -m "refactor(sessions): unified per-client profile dir + per-client meta; drop list_accounts"
```

---

### Task 4: `open_context(p, client, ...)` — drop the platform arg

**Files:**
- Modify: `src/sessions.py` (`open_context`)

**Step 1: Change the signature and body**

```python
def open_context(p, client: str, headless: bool, root: Path = PROFILES_ROOT):
    """Launch a persistent context on the CLIENT's shared profile; return (ctx, page).

    Drives installed Chrome (channel="chrome") on an ABSOLUTE user_data_dir, the
    automation switch removed and navigator.webdriver masked. Falls back to bundled
    Chromium only if Chrome isn't installed. The profile is shared by every platform —
    different domains, so logins don't collide.
    """
    pdir = profile_dir(client, root)
    pdir.mkdir(parents=True, exist_ok=True)
    kwargs = dict(
        user_data_dir=str(pdir.resolve()),
        headless=headless,
        args=_ANTI_AUTOMATION_ARGS,
        no_viewport=True,
        ignore_default_args=["--enable-automation"],
    )
    if chrome_executable():
        kwargs["channel"] = "chrome"
    ctx = p.chromium.launch_persistent_context(**kwargs)
    ctx.add_init_script(_MASK_WEBDRIVER)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return ctx, page
```

**Step 2: Commit** (this compiles; callers updated in Tasks 5/9/10/11 — run the full suite at Task 8 before relying on green)

```bash
git add src/sessions.py
git commit -m "refactor(sessions): open_context on shared per-client profile"
```

---

### Task 5: Liveness as a pure check on an open page

Replace `sessions.is_alive` (which opened its own browser per platform) with a small pure helper used by both `status` and `layout`. Navigation stays with the caller; the check only waits for the marker.

**Files:**
- Modify: `src/sessions.py` (remove `is_alive`; add `alive_on_page`)
- Test: `tests/test_sessions_alive.py` (new)

**Step 1: Write the failing test** `tests/test_sessions_alive.py`

```python
from src import sessions


class _Page:
    def __init__(self, ok):
        self.ok = ok
        self.waited = None

    def wait_for_selector(self, marker, timeout):
        self.waited = (marker, timeout)
        if not self.ok:
            raise RuntimeError("not found")


def test_alive_on_page_true_when_marker_found():
    p = _Page(ok=True)
    assert sessions.alive_on_page(p, ".x", timeout_ms=1234) is True
    assert p.waited == (".x", 1234)


def test_alive_on_page_false_when_marker_missing():
    assert sessions.alive_on_page(_Page(ok=False), ".x") is False
```

**Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_sessions_alive.py -v`
Expected: FAIL (`alive_on_page` not defined).

**Step 3: Implement in `src/sessions.py`** (delete `is_alive`, add):

```python
def alive_on_page(page, marker: str, timeout_ms: int = 8000) -> bool:
    """True if the logged-in marker appears on an already-navigated page."""
    try:
        page.wait_for_selector(marker, timeout=timeout_ms)
        return True
    except Exception:  # noqa: BLE001 — any failure means not logged in / not loaded
        return False
```

Also remove the now-stale `from playwright.sync_api import sync_playwright` import inside the deleted `is_alive`, and update the module docstring line that mentions `is_alive`.

**Step 4: Run to verify pass**

Run: `python -m pytest tests/test_sessions_alive.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/sessions.py tests/test_sessions_alive.py
git commit -m "feat(sessions): alive_on_page pure liveness check; remove per-platform is_alive"
```

---

### Task 6: `orchestrator.check_alive` over open pages (replaces `precheck`)

`precheck` called a per-platform `alive_fn` that opened browsers. The new gate takes a map of already-open pages and returns the DEAD platform names, all-or-nothing decided by the caller (`dead == []`).

**Files:**
- Modify: `src/orchestrator.py` (remove `precheck`, add `check_alive`; update module docstring)
- Test: `tests/test_orchestrator.py` (replace the two `precheck` tests)

**Step 1: Replace the failing tests** in `tests/test_orchestrator.py` — delete `test_precheck_all_alive_is_ok` and `test_precheck_one_dead_blocks_everything`, add:

```python
class _MarkerPage:
    def __init__(self, found):
        self.found = found

    def wait_for_selector(self, marker, timeout):
        if not self.found:
            raise RuntimeError("missing")


def test_check_alive_empty_when_all_found():
    pages = {"vc": _MarkerPage(True), "pikabu": _MarkerPage(True)}
    markers = {"vc": ".v", "pikabu": ".p"}
    assert orchestrator.check_alive(pages, markers, timeout_ms=10) == []


def test_check_alive_lists_dead_platforms_in_order():
    pages = {"vc": _MarkerPage(True), "pikabu": _MarkerPage(False)}
    markers = {"vc": ".v", "pikabu": ".p"}
    assert orchestrator.check_alive(pages, markers, timeout_ms=10) == ["pikabu"]
```

**Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL (`check_alive` not defined).

**Step 3: Implement in `src/orchestrator.py`** (remove `precheck` and its `Callable` import if now unused; add):

```python
def check_alive(pages_by_platform: dict, markers: dict, timeout_ms: int = 8000) -> list:
    """Return the platforms whose logged-in marker did NOT appear, in iteration order.

    `pages_by_platform` maps platform -> an already-navigated page; `markers` maps
    platform -> its alive selector. All-or-nothing is the caller's call: proceed only
    when the returned list is empty. Pure w.r.t. browser setup — pages are injected.
    """
    dead = []
    for platform, page in pages_by_platform.items():
        try:
            page.wait_for_selector(markers[platform], timeout=timeout_ms)
        except Exception:  # noqa: BLE001 — any failure = not logged in / not loaded
            dead.append(platform)
    return dead
```

**Step 4: Run to verify pass**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(orchestrator): check_alive over open pages; remove precheck"
```

---

### Task 7: `wait_until_all_closed` pumps the first LIVE page (multi-tab window)

The window now has N tabs in one context. Make the pump target the first **live** page (not `pages[0]`, which may be a closed tab while others stay open).

**Files:**
- Modify: `src/orchestrator.py` (`wait_until_all_closed`)
- Test: `tests/test_orchestrator.py` (add one test)

**Step 1: Write the failing test** (add to `tests/test_orchestrator.py`)

```python
def test_wait_pumps_a_live_page_when_first_tab_already_closed():
    closed = _FakePage(closed=True)
    live = _FakePage(closed=False)
    ctx = _FakeCtx([closed, live])  # one context, two tabs; first already closed
    pumped = []

    def pump(pg):
        pumped.append(pg)
        live.closed = True  # user closes the remaining tab

    orchestrator.wait_until_all_closed([("window", ctx)], pump=pump)
    assert pumped == [live]  # never pumped the already-closed first tab
```

**Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_orchestrator.py::test_wait_pumps_a_live_page_when_first_tab_already_closed -v`
Expected: FAIL (it pumps `pages[0]`, the closed tab).

**Step 3: Implement** — change the pump target in `wait_until_all_closed`:

```python
        try:
            ctx = live[0][1]
            page = next(pg for pg in ctx.pages if not pg.is_closed())
            pump(page)
        except Exception:  # noqa: BLE001 — window closed mid-pump; loop re-checks
            pass
```

Update the docstring: remove the "Assumes one page per context" note; state it pumps the first live page of the first live context, so a single multi-tab window is supported.

**Step 4: Run the whole orchestrator suite**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: PASS (all, including the existing wait tests).

**Step 5: Commit**

```bash
git add src/orchestrator.py tests/test_orchestrator.py
git commit -m "fix(orchestrator): wait_until_all_closed pumps first live tab (multi-tab window)"
```

---

### Task 8: `manual_login` argv for a multi-tab login Chrome (pure helper)

`login <client>` opens one plain Chrome on the client's profile with a tab per platform URL. Extract the argv construction into a pure, testable helper; keep the `subprocess.Popen` in a thin wrapper.

**Files:**
- Modify: `src/sessions.py` (`manual_login` → `_login_argv` + `manual_login`)
- Test: `tests/test_sessions_login_argv.py` (new)

**Step 1: Write the failing test** `tests/test_sessions_login_argv.py`

```python
from pathlib import Path
from src import sessions


def test_login_argv_has_profile_and_all_urls():
    argv = sessions._login_argv("C:/chrome.exe", Path("/p/acme"), ["https://a", "https://b"])
    assert argv[0] == "C:/chrome.exe"
    assert any(a.startswith("--user-data-dir=") and a.endswith("acme") for a in argv)
    assert argv[-2:] == ["https://a", "https://b"]


def test_login_argv_tolerates_no_urls():
    argv = sessions._login_argv("C:/chrome.exe", Path("/p/acme"), [])
    assert argv[0] == "C:/chrome.exe"
    assert len(argv) == 2  # exe + user-data-dir only
```

**Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_sessions_login_argv.py -v`
Expected: FAIL (`_login_argv` not defined).

**Step 3: Implement in `src/sessions.py`**

```python
def _login_argv(exe: str, pdir: Path, urls: list[str]) -> list[str]:
    return [exe, f"--user-data-dir={pdir.resolve()}", *urls]


def manual_login(client: str, urls: list[str], root: Path = PROFILES_ROOT):
    """Launch the user's plain Chrome (NO CDP) on the CLIENT's shared profile.

    Opens a tab per URL so the user can log into every platform in one sitting.
    Habr/Dzen SmartCaptcha renders blank under CDP, so login must use a plain Chrome
    process; afterwards layout/status reuse the profile via open_context. Returns the
    Popen so the caller can terminate it after login. Raises if Chrome isn't installed.
    """
    exe = chrome_executable()
    if not exe:
        raise RuntimeError("Chrome not found — install Chrome to log in.")
    pdir = profile_dir(client, root)
    pdir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(_login_argv(exe, pdir, urls))
```

**Step 4: Run to verify pass**

Run: `python -m pytest tests/test_sessions_login_argv.py -v`
Expected: PASS.

**Step 5: Run the FULL unit suite** — everything pure should be green now.

Run: `python -m pytest -v`
Expected: All PASS **except** anything in `cli.py` paths (cli has no unit tests). If `tests/test_sessions_registry.py` fails because it asserts old fields, fix only genuinely-changed assertions (registry shape is unchanged in this plan, so it should still pass).

**Step 6: Commit**

```bash
git add src/sessions.py tests/test_sessions_login_argv.py
git commit -m "feat(sessions): manual_login opens shared profile with a tab per platform"
```

---

### Task 9: `cli.py cmd_login` → `login <client>` (browser glue; manual verify)

**Files:**
- Modify: `cli.py` (`cmd_login`, and `main()` arg parser — drop the `platform` positional)

**Step 1: Rewrite `cmd_login`**

```python
def cmd_login(args):
    # One plain Chrome on the client's shared profile, a tab per platform's login/editor
    # URL. Log into the ones you need, then press Enter. NEVER publishes anything.
    urls = []
    for platform in sessions.known_platforms():
        entry = sessions.PLATFORMS[platform]
        urls.append(entry.get("login_url", entry["editor_url"]))
    proc = sessions.manual_login(args.client, urls)
    print(f"Chrome open for {args.client} with a tab per platform. Log in to the ones "
          f"you need, then come back here.")
    try:
        input("Press Enter once you're logged in to save the session...")
    except EOFError:
        time.sleep(120)
    proc.terminate()
    sessions.write_meta(args.client, {"last_login_at": _today()})
    print(f"Saved session for {args.client}.")
    return 0
```

**Step 2: Update `main()`** — the `login` subparser takes only `client`:

```python
    p_login = sub.add_parser("login", help="open one Chrome to log in to all platforms for a client")
    p_login.add_argument("client")
    p_login.set_defaults(func=cmd_login)
```

**Step 3: Manual verification** (no unit test — needs real Chrome)

Run: `python cli.py login testclient` (use `! python cli.py login testclient` so it runs in-session).
Expected: one Chrome window opens with five tabs (vc, pikabu, habr, smartlab, dzen). Log into at least VC + Habr. Press Enter. Console prints "Saved session for testclient." and `.profiles/testclient/meta.json` exists with `last_login_at`.

**Step 4: Commit**

```bash
git add cli.py
git commit -m "feat(cli): login <client> opens one Chrome to log into all platforms"
```

---

### Task 10: `cli.py cmd_status` → probe all known platforms in one context (manual verify)

**Files:**
- Modify: `cli.py` (`cmd_status`)

**Step 1: Rewrite `cmd_status`**

```python
def cmd_status(args):
    clients = [args.client] if args.client else sessions.list_clients()
    if not clients:
        print("No profiles yet. Use: python cli.py login <client>")
        return 0
    platforms = sessions.known_platforms()
    markers = {p: sessions.PLATFORMS[p]["alive_marker"] for p in platforms}
    print(f"{'client':<16}{'platform':<10}{'state':<8}label")
    with sync_playwright() as p:
        for client in clients:
            label = sessions.read_meta(client).get("label", "")
            ctx, _ = sessions.open_context(p, client, headless=True)
            try:
                pages = {}
                for platform in platforms:
                    page = ctx.new_page()
                    page.goto(sessions.PLATFORMS[platform]["editor_url"],
                              wait_until="domcontentloaded")
                    pages[platform] = page
                dead = orchestrator.check_alive(pages, markers)
            finally:
                ctx.close()
            for platform in platforms:
                state = "DEAD" if platform in dead else "alive"
                print(f"{client:<16}{platform:<10}{state:<8}{label}")
    return 0
```

> Note: one context per client (the profile can't be opened twice at once), all tabs in it. Headless is fine for probing.

**Step 2: Manual verification**

Run: `! python cli.py status testclient`
Expected: a row per platform; the ones you logged into in Task 9 show `alive`, the rest `DEAD`. Habr correctness depends on Task 12 — if Habr shows DEAD here despite being logged in, that is the known marker bug; proceed to Task 12 and re-check.

**Step 3: Commit**

```bash
git add cli.py
git commit -m "feat(cli): status probes all known platforms in one shared-profile context"
```

---

### Task 11: `cli.py cmd_layout` → single-session liveness + build (manual verify)

The heart of the change. One visible window; check all requested platforms in tabs; if all alive, build in those same tabs sequentially; leave the window open.

**Files:**
- Modify: `cli.py` (`cmd_layout`)

**Step 1: Rewrite `cmd_layout`**

```python
def cmd_layout(args):
    """Build drafts for one client across platforms in a single browser window.

    NEVER publishes: builds drafts and leaves the window open for the human to review
    and publish manually. No publish action is ever taken here.
    """
    try:
        platforms = orchestrator.parse_platforms(args.platforms, sessions.known_platforms())
    except ValueError as e:
        print(str(e))
        return 2

    slug_dir = Path("in") / args.slug
    index = slug_dir / "index.html"
    if not index.exists():
        print(f"Not found: {index}")
        return 1
    doc = parse(index.read_text(encoding="utf-8"))
    images_dir = slug_dir / "images"
    print(f"Parsed: title={doc.title!r}, blocks={len(doc.blocks)}")

    markers = {p: sessions.PLATFORMS[p]["alive_marker"] for p in platforms}
    failures = []
    with sync_playwright() as p:
        ctx, _ = sessions.open_context(p, args.client, headless=False)

        # Liveness phase (all-or-nothing): one tab per platform, navigate, check marker.
        print(f"Checking sessions for {args.client}: {', '.join(platforms)} ...")
        pages = {}
        for platform in platforms:
            page = ctx.new_page()
            page.goto(sessions.PLATFORMS[platform]["editor_url"],
                      wait_until="domcontentloaded")
            pages[platform] = page
        dead = orchestrator.check_alive(pages, markers)
        if dead:
            for platform in dead:
                print(f"DEAD: {args.client}/{platform} — run: python cli.py login {args.client}")
            print("Laid out nothing (all-or-nothing). Log in, then retry.")
            ctx.close()
            return 1

        # Build phase: same tabs, sequential (real-clipboard paste can't run in parallel).
        contexts = [("window", ctx)]
        for platform in platforms:
            print(f"--- {args.client}/{platform} ---")
            try:
                sessions.PLATFORMS[platform]["build_document"](pages[platform], doc, images_dir)
                print(f"Done — {platform} draft built. Review and publish manually.")
            except Exception as e:  # noqa: BLE001 — report and continue to next platform
                failures.append((platform, repr(e)))
                print(f"FAILED {platform}: {e!r} (tab left open)")

        print(
            f"\nAll {len(platforms)} tab(s) open in one window. Review and publish "
            "manually. Nothing closes on its own — close the window yourself when done "
            "(Ctrl+C also exits)."
        )
        orchestrator.wait_until_all_closed(contexts, pump=lambda pg: pg.wait_for_timeout(500))

    if failures:
        print("Failures: " + ", ".join(f"{p}: {err}" for p, err in failures))
        return 1
    return 0
```

> Every `build_document` takes `(page, doc, images_dir)` and navigates to its own editor as needed (e.g. Habr → `NEW_ARTICLE_URL`), so reusing the liveness tab is correct.

**Step 2: Manual verification — happy path**

Pick an existing slug under `in/` (e.g. the one used to validate earlier adapters).
Run: `! python cli.py layout <slug> testclient vc,habr`
Expected: ONE Chrome window opens with two tabs; both pass the liveness check; VC draft built in its tab, Habr draft built in its tab; console says all tabs open; the window stays open until you close it. Verify each tab shows the built draft. Nothing is published.

**Step 3: Manual verification — all-or-nothing**

Log out of one platform (or use a platform you never logged into) and run a layout that includes it.
Expected: console prints `DEAD: testclient/<platform> — run: python cli.py login testclient`, the window closes, exit code 1, and NOTHING was built in any tab.

**Step 4: Commit**

```bash
git add cli.py
git commit -m "feat(cli): layout builds all platforms as tabs in one window (single session)"
```

---

### Task 12: Fix Habr `ALIVE_SEL` so liveness is accurate

The navbar pencil became a `<button>` popup, so `ALIVE_SEL = "a:has(svg...)"` never matches → false DEAD, which blocks the whole all-or-nothing run when Habr is requested. Use the editor body at the new-article URL as the logged-in marker — it is the same selector `build_document` already relies on and only mounts for a logged-in user.

**Files:**
- Modify: `src/habr_adapter.py` (decouple `ALIVE_SEL` from `PENCIL_SEL`)
- Modify: `src/sessions.py` (Habr entry: `editor_url` → `NEW_ARTICLE_URL`)
- Verify: `tests/test_sessions_registry.py` still passes (shape unchanged)

**Step 1: In `src/habr_adapter.py`**, keep `PENCIL_SEL` (still used as the build fallback at line ~184) but point the liveness marker at the editor body:

```python
# Liveness: the editor body only mounts for a logged-in user. The old navbar-pencil
# selector broke when the pencil became a <button> popup, so we check the editor body
# at the new-article URL instead (the same selector build_document waits for).
ALIVE_SEL = BODY_SEL
```

(`BODY_SEL = ".tiptap.ProseMirror"` is defined a few lines below today — move the `ALIVE_SEL = BODY_SEL` line to AFTER `BODY_SEL` is defined.)

**Step 2: In `src/sessions.py`**, change the Habr entry so liveness navigates to the editor (where `BODY_SEL` appears), and update the comment:

```python
    "habr": {
        "build_document": habr_adapter.build_document,
        # Liveness navigates to the new-article editor and waits for the editor body
        # (ALIVE_SEL = BODY_SEL), which mounts only for a logged-in user.
        "editor_url": habr_adapter.NEW_ARTICLE_URL,
        "alive_marker": habr_adapter.ALIVE_SEL,
        "manual_login": True,
        "login_url": habr_adapter.LOGIN_URL,
    },
```

**Step 3: Run the registry test**

Run: `python -m pytest tests/test_sessions_registry.py -v`
Expected: PASS (entry still has callable `build_document`, http `editor_url`, truthy `alive_marker`, `manual_login is True`).

**Step 4: Manual verification (the bug fix)**

Run: `! python cli.py status testclient` with Habr logged in.
Expected: Habr now shows `alive` (previously falsely `DEAD`). Then run `! python cli.py layout <slug> testclient habr` and confirm liveness passes and the Habr draft builds.

> If `BODY_SEL` does NOT appear when logged in (e.g. Habr redirects new-article to a sandbox URL for fresh accounts), fall back to the navbar marker in its button form: `ALIVE_SEL = "button:has(svg.tm-header-user-menu__icon_write)"` and keep `editor_url = HOME_URL`. Verify whichever you choose against the live logged-in page before committing — per @superpowers:verification-before-completion, do not claim fixed without seeing `alive`.

**Step 5: Commit**

```bash
git add src/habr_adapter.py src/sessions.py
git commit -m "fix(habr): liveness marker = editor body (pencil is now a button popup)"
```

---

### Task 13: Migration cleanup + full end-to-end validation

**Files:**
- Modify: `src/sessions.py` module docstring (describe the shared-profile model; remove stale per-platform/`is_alive` wording)
- Modify: `docs/platform-notes.md` (one line: profiles are now per-client shared)

**Step 1: One-time profile migration (manual)**

For each real client you use, the old per-platform dirs `.profiles/<client>/<platform>/` are now stale. The shared profile is `.profiles/<client>/` itself. Run `python cli.py login <client>` once to log in within the shared profile, then delete the old per-platform subfolders:

```powershell
Remove-Item -Recurse -Force .profiles/<client>/vc, .profiles/<client>/pikabu, .profiles/<client>/habr, .profiles/<client>/smartlab, .profiles/<client>/dzen -ErrorAction SilentlyContinue
```

> Only delete subfolders that are the OLD per-platform dirs. Do not delete Chrome's own files (`Default/`, `Local State`, etc.) that the shared profile creates at `.profiles/<client>/`.

**Step 2: Update docstrings/notes** to match the shared-profile reality (sessions.py header currently says "stored at `.profiles/<client>/<platform>/`" and references `is_alive`).

**Step 3: Full unit suite**

Run: `python -m pytest -v`
Expected: ALL PASS.

**Step 4: Full manual end-to-end**

Run: `! python cli.py layout <slug> <realclient> all`
Expected: one window, a tab per platform, all pass liveness, all drafts build sequentially, window stays open, nothing published. Spot-check each tab.

**Step 5: Commit**

```bash
git add src/sessions.py docs/platform-notes.md
git commit -m "docs(sessions): document shared per-client profile model; migration notes"
```

---

## Done criteria

- `python -m pytest -v` all green.
- `login <client>` logs into all platforms in one Chrome; `status` reports accurate alive/DEAD (Habr included); `layout <slug> <client> <platforms>` opens ONE window with a tab per platform, builds sequentially, leaves it open, all-or-nothing on dead sessions.
- No code path ever publishes. The NEVER-publish rule is recorded in `docs/platform-notes.md`, `cmd_layout`'s docstring, and the design doc.

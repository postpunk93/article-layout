# Session Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let the user run "lay out article X for client Y on platforms 1,2,3" from a Claude session, with per-`(client, platform)` browser profiles, explicit liveness checks, and a separate manual `login` step.

**Architecture:** A new `src/sessions.py` owns all profile logic (paths, persistent contexts, liveness probe, `meta.json`). Adapters drop their hardcoded `PROFILE_DIR`/`run_document` and just expose the already-pure `build_document(page, doc, images_dir)`. A single `cli.py` exposes `login` / `status` / `layout`; `layout` is all-or-nothing on a liveness pre-check. Folders under `.profiles/<client>/<platform>/` are the source of truth.

**Tech Stack:** Python 3, Playwright (sync), pytest. Windows + PowerShell shell.

**Reference:** `docs/plans/2026-05-29-session-management-design.md` (approved design).

---

## Conventions for the executor

- Run tests with `python -m pytest <path> -v` from `C:\Projects\article-layout`.
- The pure helpers take an optional `root` argument so tests use `tmp_path` instead of the real `.profiles/`. Production callers omit it (defaults to `PROFILES_ROOT`).
- Browser code (`open_context`, `is_alive`, the `login`/`status`/`layout` browser paths) is NOT unit-tested — same policy as the existing adapters (covered by manual run / `verify`). We DO unit-test every pure decision around it.
- Commit after every task. Keep commits small.

---

## Task 1: Pure profile helpers in `src/sessions.py`

**Files:**
- Create: `src/sessions.py`
- Test: `tests/test_sessions_paths.py`

**Step 1: Write the failing tests**

```python
# tests/test_sessions_paths.py
from pathlib import Path

from src import sessions


def test_profile_dir_builds_client_platform_path():
    root = Path("/tmp/profiles")
    assert sessions.profile_dir("acme", "vc", root=root) == root / "acme" / "vc"


def test_list_clients_reads_folder_names(tmp_path):
    (tmp_path / "acme" / "vc").mkdir(parents=True)
    (tmp_path / "beta" / "pikabu").mkdir(parents=True)
    assert sessions.list_clients(root=tmp_path) == ["acme", "beta"]


def test_list_clients_empty_when_root_missing(tmp_path):
    assert sessions.list_clients(root=tmp_path / "nope") == []


def test_list_accounts_reads_platform_folders(tmp_path):
    (tmp_path / "acme" / "vc").mkdir(parents=True)
    (tmp_path / "acme" / "pikabu").mkdir(parents=True)
    assert sessions.list_accounts("acme", root=tmp_path) == ["pikabu", "vc"]


def test_list_accounts_empty_for_unknown_client(tmp_path):
    assert sessions.list_accounts("ghost", root=tmp_path) == []
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sessions_paths.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.sessions'`).

**Step 3: Write minimal implementation**

```python
# src/sessions.py
"""Single owner of browser-profile logic for the article-layout adapters.

A profile is a persistent Chromium context stored at
`.profiles/<client>/<platform>/`. The folder existing IS the fact that the
account is set up — there is no central registry. Per-profile metadata lives
in a `meta.json` beside the context. Liveness is never cached: `is_alive`
probes the live site every time.
"""
from pathlib import Path

PROFILES_ROOT = Path(".profiles")


def profile_dir(client: str, platform: str, root: Path = PROFILES_ROOT) -> Path:
    return Path(root) / client / platform


def list_clients(root: Path = PROFILES_ROOT) -> list[str]:
    root = Path(root)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def list_accounts(client: str, root: Path = PROFILES_ROOT) -> list[str]:
    client_dir = Path(root) / client
    if not client_dir.exists():
        return []
    return sorted(p.name for p in client_dir.iterdir() if p.is_dir())
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sessions_paths.py -v`
Expected: PASS (5 passed).

**Step 5: Commit**

```bash
git add src/sessions.py tests/test_sessions_paths.py
git commit -m "feat(sessions): profile_dir + list_clients/list_accounts"
```

---

## Task 2: `meta.json` read/write round-trip

**Files:**
- Modify: `src/sessions.py`
- Test: `tests/test_sessions_meta.py`

**Step 1: Write the failing tests**

```python
# tests/test_sessions_meta.py
from src import sessions


def test_read_meta_missing_returns_empty_dict(tmp_path):
    assert sessions.read_meta("acme", "vc", root=tmp_path) == {}


def test_write_then_read_meta_round_trip(tmp_path):
    sessions.write_meta("acme", "vc", {"label": "ACME", "login": "a@b.c"}, root=tmp_path)
    assert sessions.read_meta("acme", "vc", root=tmp_path) == {"label": "ACME", "login": "a@b.c"}


def test_write_meta_creates_profile_dir(tmp_path):
    sessions.write_meta("new", "pikabu", {"label": "x"}, root=tmp_path)
    assert (tmp_path / "new" / "pikabu" / "meta.json").is_file()


def test_write_meta_merges_with_existing(tmp_path):
    sessions.write_meta("acme", "vc", {"label": "ACME"}, root=tmp_path)
    sessions.write_meta("acme", "vc", {"last_login_at": "2026-05-29"}, root=tmp_path)
    meta = sessions.read_meta("acme", "vc", root=tmp_path)
    assert meta == {"label": "ACME", "last_login_at": "2026-05-29"}
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sessions_meta.py -v`
Expected: FAIL (`AttributeError: module 'src.sessions' has no attribute 'read_meta'`).

**Step 3: Write minimal implementation**

Add to `src/sessions.py` (add `import json` at the top):

```python
def _meta_path(client: str, platform: str, root: Path = PROFILES_ROOT) -> Path:
    return profile_dir(client, platform, root) / "meta.json"


def read_meta(client: str, platform: str, root: Path = PROFILES_ROOT) -> dict:
    path = _meta_path(client, platform, root)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_meta(client: str, platform: str, updates: dict, root: Path = PROFILES_ROOT) -> dict:
    """Merge `updates` into the profile's meta.json (creating the dir) and return it."""
    pdir = profile_dir(client, platform, root)
    pdir.mkdir(parents=True, exist_ok=True)
    meta = read_meta(client, platform, root)
    meta.update(updates)
    (pdir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sessions_meta.py -v`
Expected: PASS (4 passed).

**Step 5: Commit**

```bash
git add src/sessions.py tests/test_sessions_meta.py
git commit -m "feat(sessions): meta.json read/write round-trip"
```

---

## Task 3: Platform registry + drop adapter `PROFILE_DIR`/`run_document`

The registry maps a platform key to its adapter's `build_document`, the editor URL, and the `alive_marker` selector (present only when logged in). Adapters lose their `PROFILE_DIR` constant and `run_document` wrapper (context creation moves to `sessions.open_context`, Task 4).

**Files:**
- Modify: `src/sessions.py`
- Modify: `src/vc_adapter.py` (remove `PROFILE_DIR` line 20; remove `run_document`, lines 225-246)
- Modify: `src/pikabu_adapter.py` (remove `PROFILE_DIR` line 26; remove `run_document`, lines 232-249)
- Test: `tests/test_sessions_registry.py`

**Step 1: Write the failing tests**

```python
# tests/test_sessions_registry.py
from src import sessions


def test_registry_has_vc_and_pikabu():
    assert set(sessions.PLATFORMS) == {"vc", "pikabu"}


def test_each_platform_entry_is_complete():
    for key, entry in sessions.PLATFORMS.items():
        assert callable(entry["build_document"]), key
        assert entry["editor_url"].startswith("http"), key
        assert entry["alive_marker"], key


def test_known_platforms_helper():
    assert sessions.known_platforms() == ["pikabu", "vc"]
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sessions_registry.py -v`
Expected: FAIL (`AttributeError: module 'src.sessions' has no attribute 'PLATFORMS'`).

**Step 3: Implement**

Add to `src/sessions.py` (top-level imports):

```python
from src import vc_adapter, pikabu_adapter

PLATFORMS = {
    "vc": {
        "build_document": vc_adapter.build_document,
        "editor_url": "https://vc.ru/?modal=editor",
        # The title field only renders inside the editor when logged in.
        "alive_marker": 'div.editor-tool-input[data-placeholder="Заголовок"]',
    },
    "pikabu": {
        "build_document": pikabu_adapter.build_document,
        "editor_url": "https://pikabu.ru/add",
        # The Tiptap editor body only mounts for a logged-in user.
        "alive_marker": ".tiptap.ProseMirror",
    },
}


def known_platforms() -> list[str]:
    return sorted(PLATFORMS)
```

Then in `src/vc_adapter.py`: delete the `PROFILE_DIR = ".vc-profile"` line and the entire `run_document(...)` function (lines ~225-246). Leave `EDITOR_URL`/`TITLE_SEL` etc. and `build_document` intact.

In `src/pikabu_adapter.py`: delete the `PROFILE_DIR = ".pikabu-profile"` line and the entire `run_document(...)` function (lines ~232-249). Leave `ADD_URL`/`BODY_SEL` etc. and `build_document` intact.

**Step 4: Run the full suite to verify nothing else broke**

Run: `python -m pytest -v`
Expected: PASS, including the new registry tests. (If any test imported `run_document` or `PROFILE_DIR`, update it — grep first: `git grep -n "run_document\|PROFILE_DIR" tests src`.)

**Step 5: Commit**

```bash
git add src/sessions.py src/vc_adapter.py src/pikabu_adapter.py tests/test_sessions_registry.py
git commit -m "feat(sessions): PLATFORMS registry; drop adapter PROFILE_DIR/run_document"
```

---

## Task 4: `open_context` + `is_alive` (browser; manual verify)

No unit tests (browser). Implement carefully and verify by hand at the end of the task.

**Files:**
- Modify: `src/sessions.py`

**Step 1: Implement**

Add to `src/sessions.py` (top: `import time`):

```python
def open_context(p, client: str, platform: str, headless: bool, root: Path = PROFILES_ROOT):
    """Launch a persistent Chromium context on this profile and return (ctx, page)."""
    pdir = profile_dir(client, platform, root)
    pdir.mkdir(parents=True, exist_ok=True)
    ctx = p.chromium.launch_persistent_context(
        str(pdir), headless=headless, args=["--start-maximized"], no_viewport=True
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return ctx, page


def is_alive(client: str, platform: str, headless: bool = True,
             timeout_ms: int = 8000, root: Path = PROFILES_ROOT) -> bool:
    """Probe the live site: open the editor and look for the logged-in marker.

    No cache — cookies can expire server-side at any time, so we always check.
    A missing profile folder counts as dead (needs login).
    """
    from playwright.sync_api import sync_playwright

    if not profile_dir(client, platform, root).exists():
        return False
    entry = PLATFORMS[platform]
    with sync_playwright() as p:
        ctx, page = open_context(p, client, platform, headless=headless, root=root)
        try:
            page.goto(entry["editor_url"], wait_until="domcontentloaded")
            page.wait_for_selector(entry["alive_marker"], timeout=timeout_ms)
            return True
        except Exception:
            return False
        finally:
            ctx.close()
```

**Step 2: Manual verify (run by the human, not the harness)**

With a currently-logged-in profile migrated in Task 7, suggest the user run:
`! python -c "from src import sessions; print(sessions.is_alive('default','pikabu'))"`
Expected: `True` for a live session; `False` after logging out / for a missing folder.

**Step 3: Commit**

```bash
git add src/sessions.py
git commit -m "feat(sessions): open_context + is_alive liveness probe"
```

---

## Task 5: `layout` decision core + platform arg parsing (pure, TDD)

Factor the all-or-nothing decision and the `<platforms>` parsing into pure functions so they're unit-tested without a browser. The CLI (Task 6) calls these, then drives the browser.

**Files:**
- Create: `src/orchestrator.py`
- Test: `tests/test_orchestrator.py`

**Step 1: Write the failing tests**

```python
# tests/test_orchestrator.py
import pytest

from src import orchestrator


def test_parse_platforms_explicit_list():
    assert orchestrator.parse_platforms("vc,pikabu", ["pikabu", "vc"]) == ["vc", "pikabu"]


def test_parse_platforms_all_expands_to_known():
    assert orchestrator.parse_platforms("all", ["pikabu", "vc"]) == ["pikabu", "vc"]


def test_parse_platforms_rejects_unknown():
    with pytest.raises(ValueError) as e:
        orchestrator.parse_platforms("vc,telegram", ["pikabu", "vc"])
    assert "telegram" in str(e.value)


def test_precheck_all_alive_is_ok():
    alive = lambda c, p: True
    ok, dead = orchestrator.precheck("acme", ["vc", "pikabu"], alive)
    assert ok is True
    assert dead == []


def test_precheck_one_dead_blocks_everything():
    alive = lambda c, p: p != "pikabu"
    ok, dead = orchestrator.precheck("acme", ["vc", "pikabu"], alive)
    assert ok is False
    assert dead == [("acme", "pikabu")]
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.orchestrator'`).

**Step 3: Implement**

```python
# src/orchestrator.py
"""Pure decision logic for the `layout` command — no browser here.

`parse_platforms` validates the user's platform argument; `precheck` runs the
all-or-nothing liveness gate. The CLI wires these to the real `is_alive` and to
the browser; tests inject fakes.
"""
from typing import Callable


def parse_platforms(arg: str, known: list[str]) -> list[str]:
    if arg == "all":
        return list(known)
    requested = [s.strip() for s in arg.split(",") if s.strip()]
    unknown = [p for p in requested if p not in known]
    if unknown:
        raise ValueError(f"unknown platform(s): {', '.join(unknown)}; known: {', '.join(known)}")
    return requested


def precheck(client: str, platforms: list[str],
             alive_fn: Callable[[str, str], bool]):
    """Return (ok, dead) where dead is a list of (client, platform) tuples.

    ok is True only if EVERY requested session is alive (all-or-nothing).
    """
    dead = [(client, p) for p in platforms if not alive_fn(client, p)]
    return (not dead, dead)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: PASS (5 passed).

**Step 5: Commit**

```bash
git add src/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(orchestrator): parse_platforms + all-or-nothing precheck"
```

---

## Task 6: `cli.py` — `login` / `status` / `layout`

Thin command layer wiring Tasks 1-5 to argparse and the browser. Browser paths verified manually.

**Files:**
- Create: `cli.py`
- Reference for parse/build flow: `run_vc.py:17-32`, `run_pikabu.py:17-32` (to be deleted in Task 7).

**Step 1: Implement**

```python
# cli.py
"""Unified entry point for the article-layout adapters.

  python cli.py login  <client> <platform>
  python cli.py status [client]
  python cli.py layout <slug> <client> <platforms>   # platforms: vc,pikabu | all

`login` is interactive (run it yourself: `! python cli.py login acme pikabu`).
`layout` checks every requested session first; if any is dead it lays out
NOTHING and tells you who to log in.
"""
import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from src import sessions, orchestrator
from src.parser import parse


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def cmd_login(args):
    platform = args.platform
    if platform not in sessions.PLATFORMS:
        print(f"Unknown platform {platform!r}; known: {', '.join(sessions.known_platforms())}")
        return 2
    entry = sessions.PLATFORMS[platform]
    with sync_playwright() as p:
        ctx, page = sessions.open_context(p, args.client, platform, headless=False)
        page.goto(entry["editor_url"], wait_until="domcontentloaded")
        print(f"Browser open for {args.client}/{platform}. Log in, then come back here.")
        try:
            input("Press Enter once you're logged in to save the session...")
        except EOFError:
            time.sleep(120)
        ctx.close()
    sessions.write_meta(args.client, platform, {"last_login_at": _today()})
    print(f"Saved session for {args.client}/{platform}.")
    return 0


def cmd_status(args):
    clients = [args.client] if args.client else sessions.list_clients()
    if not clients:
        print("No profiles yet. Use: python cli.py login <client> <platform>")
        return 0
    print(f"{'client':<16}{'platform':<10}{'state':<8}label")
    for client in clients:
        for platform in sessions.list_accounts(client):
            state = "alive" if sessions.is_alive(client, platform) else "DEAD"
            label = sessions.read_meta(client, platform).get("label", "")
            print(f"{client:<16}{platform:<10}{state:<8}{label}")
    return 0


def cmd_layout(args):
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

    print(f"Checking sessions for {args.client}: {', '.join(platforms)} ...")
    ok, dead = orchestrator.precheck(args.client, platforms, sessions.is_alive)
    if not ok:
        for client, platform in dead:
            print(f"DEAD: {client}/{platform} — run: python cli.py login {client} {platform}")
        print("Laid out nothing (all-or-nothing). Log in the dead sessions, then retry.")
        return 1

    failures = []
    for platform in platforms:
        entry = sessions.PLATFORMS[platform]
        print(f"--- {args.client}/{platform} ---")
        with sync_playwright() as p:
            ctx, page = sessions.open_context(p, args.client, platform, headless=False)
            try:
                entry["build_document"](page, doc, images_dir)
                print(f"Done — {platform} draft built. Review and publish manually.")
            except Exception as e:  # noqa: BLE001 — report and continue to next platform
                failures.append((platform, repr(e)))
                print(f"FAILED {platform}: {e!r} (window left open)")
            try:
                input(f"Press Enter to close {platform} browser...")
            except EOFError:
                time.sleep(15)
            ctx.close()

    if failures:
        print("Failures: " + ", ".join(f"{p}: {err}" for p, err in failures))
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(prog="cli.py")
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="open a browser to log in to a (client, platform)")
    p_login.add_argument("client")
    p_login.add_argument("platform")
    p_login.set_defaults(func=cmd_login)

    p_status = sub.add_parser("status", help="show alive/dead per session")
    p_status.add_argument("client", nargs="?")
    p_status.set_defaults(func=cmd_status)

    p_layout = sub.add_parser("layout", help="lay out in/<slug> for a client on platforms")
    p_layout.add_argument("slug")
    p_layout.add_argument("client")
    p_layout.add_argument("platforms", help="comma list (vc,pikabu) or 'all'")
    p_layout.set_defaults(func=cmd_layout)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
```

**Step 2: Smoke-test arg parsing (no browser)**

Run: `python cli.py layout missingslug default vc,telegram`
Expected: prints `unknown platform(s): telegram; known: pikabu, vc` and exits 2.

Run: `python cli.py layout missingslug default vc`
Expected: prints `Not found: in\missingslug\index.html` and exits 1.

**Step 3: Commit**

```bash
git add cli.py
git commit -m "feat(cli): unified login/status/layout entry point"
```

---

## Task 7: Migrate profiles, update .gitignore, remove old runners

Preserve current logins by moving the existing profiles into client `default`.

**Files:**
- Move: `.vc-profile/` → `.profiles/default/vc/`; `.pikabu-profile/` → `.profiles/default/pikabu/`
- Modify: `.gitignore`
- Delete: `run_vc.py`, `run_pikabu.py`, `login_pikabu.py`

**Step 1: Move the profile folders (PowerShell)**

These are runtime data, not git-tracked (gitignored), so this is a filesystem move. Run only if the folders exist:

```powershell
New-Item -ItemType Directory -Force .profiles\default | Out-Null
if (Test-Path .vc-profile)     { Move-Item .vc-profile     .profiles\default\vc }
if (Test-Path .pikabu-profile) { Move-Item .pikabu-profile .profiles\default\pikabu }
```

**Step 2: Update `.gitignore`**

Replace these two lines:
```
.vc-profile/
.pikabu-profile/
```
with one line:
```
.profiles/
```

**Step 3: Delete the old runners**

```bash
git rm run_vc.py run_pikabu.py login_pikabu.py
```
(`login_pikabu.py` is currently untracked — if `git rm` errors on it, delete it with `Remove-Item login_pikabu.py`.)

**Step 4: Verify nothing references the deleted files / constants**

Run: `git grep -n "run_vc\|run_pikabu\|login_pikabu\|PROFILE_DIR\|run_document"`
Expected: no hits in `src/`, `cli.py`, or `tests/` (docs/experiments may still mention them — that's fine).

Run: `python -m pytest -v`
Expected: full suite PASS.

**Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore(sessions): migrate profiles to .profiles/default, drop old runners"
```

---

## Task 8: End-to-end manual verification (human-run)

Not automated. Suggest the user run, via the `!` prefix:

1. `! python cli.py status`
   Expected: a table showing `default · vc` and `default · pikabu` as `alive` (assuming the migrated sessions are still valid).
2. `! python cli.py layout lists-quotes default vc,pikabu`
   Expected: pre-check passes, both editors open and build drafts, windows stay open. If a session is dead, expect `DEAD: default/<platform>` and nothing laid out.
3. Add a new account: `! python cli.py login <newclient> vc` → log in → `! python cli.py status <newclient>` shows it alive.

Record the outcome; update the `project_pikabu_adapter` / project memory if behaviour facts change.

---

## Done criteria

- `python -m pytest -v` is green (existing 52+ tests plus the new pure tests for paths, meta, registry, orchestrator).
- `cli.py` `login` / `status` / `layout` work against real profiles; `layout` is all-or-nothing.
- `.profiles/<client>/<platform>/` is the only profile store; `meta.json` holds metadata; `.gitignore` ignores `.profiles/`.
- `run_vc.py`, `run_pikabu.py`, `login_pikabu.py` are gone; no code references `PROFILE_DIR` or `run_document`.

# Unified profile: lay out all platforms in one browser window

**Date:** 2026-06-01
**Status:** Design approved, pending implementation
**Branch:** `feat/unified-profile-parallel-layout`

> **NON-NEGOTIABLE — this project NEVER publishes.** Every adapter stops at a
> built draft (+ autosave where the platform has it) and leaves the window open.
> The final "publish" action is always a human's. Whatever we change in the
> pipeline, no publish button is ever clicked. If this ever changes, the user
> will say so separately and explicitly.

## Problem

`cli.py layout` opens **one Chrome window per platform** because profiles are
stored per platform at `.profiles/<client>/<platform>/` — each is its own
`user-data-dir`, hence its own Chrome process/window. The user wants all
requested platforms laid out **in one browser window** (a tab per platform) and
left open. This is the backlog item recorded in
`2026-06-01-browser-lifecycle-keep-open-design.md`.

A single running Chrome can only use **one** `user-data-dir`; separate profile
dirs cannot be merged into one window. But the platforms live on **different
domains** (habr.com, vc.ru, dzen.ru, …), so a single profile can be logged into
all of them at once without cookie conflict. Therefore "one window" ⇒ **one
shared Chrome profile per client**.

## Goal

`layout <slug> <client> <platforms>` opens **one** Chrome window on the client's
profile, builds each platform's draft in **its own tab** (sequentially), and
leaves the whole window with all tabs open. Nothing auto-closes, nothing
publishes. Two clients ⇒ two separate `layout` runs ⇒ two windows (one per
client) — profiles of different clients must stay isolated.

## Decisions (from brainstorming)

- **Unified profile per client.** `profile_dir(client)` → `.profiles/<client>/`
  (drop the platform component). One Chrome profile logged into every platform.
  Migration cost accepted: a one-time re-login into the platforms inside the new
  shared profile.
- **`login <client>` — single sitting.** Opens a plain (non-CDP) Chrome on the
  client's profile with a tab per known platform's login/editor URL; the user
  logs into the ones they need and presses Enter to save. Non-CDP Chrome keeps
  the Habr/Dzen SmartCaptcha login working for the whole profile at once.
- **Approach A — single session.** One visible Chrome window for the whole
  `layout` run: check liveness per platform in tabs, and if all are alive, build
  the drafts in those same tabs. All-or-nothing preserved. (Rejected: B — a
  separate headless precheck that reopens the profile, slower and opens the
  locked profile twice; C — no precheck, build-and-catch, which loses clean
  all-or-nothing because tabs half-build before a dead session is noticed.)
- **Sequential builds.** Tabs are filled one at a time: VC/Dzen/Habr paste via
  the real system clipboard + window focus, so concurrent builds would fight
  over the clipboard/focus.
- **Fix Habr `ALIVE_SEL` in scope.** Memory: Habr's liveness marker falsely
  reports DEAD. Under all-or-nothing that blocks the entire run whenever Habr is
  requested, so the feature does not work for Habr until the marker points at an
  element actually present for a logged-in user.

## Scope

- **Changes:** `sessions.py` (profile path, `open_context`, liveness split,
  `manual_login`), `orchestrator.py` (`precheck` → `check_alive` on open pages,
  `wait_until_all_closed` for one context), `cli.py` (all three commands),
  `habr_adapter.ALIVE_SEL`.
- **Unchanged:** the parser, IR, `emit_html`, and the per-platform
  `build_document` bodies (each still navigates to its own editor and stops at a
  draft).

## Design

### Profile model

- `profile_dir(client)` → `.profiles/<client>/` — the Chrome `user-data-dir`.
- `meta.json` moves to `.profiles/<client>/meta.json` (per client). `last_login_at`
  written by `login`.
- Per-platform folders are gone; "which platforms a client has" is no longer
  folder-derived. `PLATFORMS` (editor_url, alive_marker, build_document) is
  unchanged; the per-platform `manual_login`/`login_url` flags stop gating login
  (login is now always one manual Chrome for the whole profile).

### `login <client>`

Open a plain Chrome (no CDP) on `.profiles/<client>/` with a tab per known
platform's login/editor URL. The user logs into the platforms they need, presses
Enter; we terminate Chrome and write `last_login_at`. Captcha platforms work
because this Chrome is not CDP-driven.

### `status [client]`

Liveness is no longer folder-derived, so `status` **probes every known platform**
in the client's profile. Open **one** context (the profile can't be opened twice
at once), navigate each platform's `editor_url` in a tab, check its
`alive_marker`, print alive/DEAD per platform.

### `layout <slug> <client> <platforms>` — single session (Approach A)

1. Parse `in/<slug>/index.html` → `doc` (unchanged).
2. `open_context(p, client, headless=False)` → one visible window / one context.
3. **Liveness phase (all-or-nothing).** For each requested platform open a tab
   (`ctx.new_page()`), goto `editor_url`, wait for `alive_marker` with a timeout
   → build an alive/DEAD map. If any is DEAD: print which to log in
   (`python cli.py login <client>`), **close the window, build nothing**, exit 1.
4. **Build phase.** All alive → in the **same** tabs, call
   `build_document(page, doc, images_dir)` **sequentially**. `build_document`
   navigates to its own editor as needed (e.g. Habr's direct editor URL).
5. Print summary; **leave the one window with all tabs open**;
   `wait_until_all_closed` waits until the user closes the window. The script
   never calls `ctx.close()` on success and never publishes.

### Code structure

- **`sessions.py`**
  - `profile_dir(client)`, `open_context(p, client, ...)` (no platform arg).
  - Split `is_alive`: `_alive_on_page(page, marker, timeout)` (pure check on an
    open tab) + a thin wrapper for `status` that opens one context and probes a
    list of platforms.
  - `manual_login(client, urls)` opens Chrome on the client's profile with the
    given tabs.
- **`orchestrator.py`**
  - `parse_platforms` unchanged.
  - `precheck` → `check_alive(pages_by_platform, markers, timeout)` returning the
    DEAD list, operating on already-open tabs (raises no `sync_playwright` of its
    own).
  - `wait_until_all_closed` adapted to **one** context with N tabs (waits for the
    window to close, polling `page.is_closed()` across `ctx.pages`).
- **`cli.py`**: `cmd_layout` rewritten for the single session (steps 2–5);
  `cmd_login` → `login <client>`; `cmd_status` → one-context probe of all
  platforms. `cmd_layout` docstring restates the NEVER-publish rule.
- **`habr_adapter.ALIVE_SEL`** repointed at a logged-in-only element that is
  actually present (verified against the live page during implementation).

### Migration

The shared profile is `.profiles/<client>/` itself. Take the clean path: run
`login <client>` once and log into the needed platforms in the new shared
profile; delete the old per-platform subfolders as part of migration. The
re-login is one-time and already accepted.

### Error handling

- DEAD session in the liveness phase → window closes, message says
  `python cli.py login <client>`, nothing is built, exit 1.
- `build_document` raises in the build phase → that tab is **left open**, the
  failure is recorded, remaining platforms continue (current behavior). Summary
  of failures prints after the window closes; exit 1 if any failed, else 0.
- Chrome not installed → unchanged (raise / message as today).

## Testing

Pure logic, injected fakes, no real browser (mirrors `tests/test_orchestrator.py`):

- `profile_dir(client)` → `.profiles/<client>`.
- `check_alive(...)` on fake pages: returns the correct DEAD list; empty when all
  markers found.
- `parse_platforms` (unchanged) regression.
- `wait_until_all_closed` on a fake one-context/N-tabs: does not return while any
  tab is open; returns once all closed; survives a tab closing mid-poll.
- Update existing `test_sessions_paths` / `test_sessions_registry` /
  `test_sessions_meta` / `test_orchestrator` to the new signatures.

The browser-driven run (real Chrome + logins, Habr `ALIVE_SEL`) is validated
manually end-to-end, like every adapter.

## Repo note: never publish

Add an explicit NON-NEGOTIABLE block to the top of `docs/platform-notes.md`, a
short restatement in the `cmd_layout` docstring in `cli.py`, and this same rule
in the header of this design doc (above).

# Browser lifecycle: keep windows open, never auto-close

**Date:** 2026-06-01
**Status:** Design approved, pending implementation
**Branch:** `feat/browser-keep-open`

## Problem

`cli.py layout` processes platforms strictly one at a time: each iteration opens a
fresh `sync_playwright()` + context, builds the draft, then waits on
`input("Press Enter to close…")` and calls `ctx.close()`. Two pains:

1. **Lost work.** When `layout` runs without a live TTY (e.g. from the
   article-pipeline skill or with redirected stdin), `input()` raises `EOFError`,
   the code sleeps 15s and **closes the window**. Habr does not autosave its
   draft, so advancing to the settings screen and then losing the window throws
   the work away.
2. **No "review everything at once".** Windows are closed before the next
   platform opens, so you can never see all platforms side by side.

## Goal

Order layout for N platforms → each platform opens in its **own Chrome window**,
all windows stay open simultaneously at the end, and **nothing closes on its
own**. The user reviews/publishes manually and closes the windows themselves.
Publishing remains manual (unchanged).

## Decisions (from brainstorming)

- **Window model: multiple windows, no re-login.** Profiles stay isolated per
  platform (`.profiles/<client>/<platform>/`), so each platform is its own Chrome
  process/window. Tabs-in-one-window is deferred (see Backlog).
- **Close behavior: never auto-close.** Windows close only when the user closes
  them by hand. The script must not call `ctx.close()` itself and must not have
  any EOF/timeout-triggered close path. `Ctrl+C` is the only forced exit.
- **Approach A** chosen over detaching Chrome (B) or per-platform background
  processes (C): a single shared `sync_playwright()` keeps Playwright in control
  for the whole run, which is required because the build itself (clipboard paste
  + image upload) is driven by Playwright. A live Playwright context cannot be
  handed off to an orphaned process, so "true detach" (B) is infeasible.

## Scope

- **Changes:** `cmd_layout` in `cli.py` + one new helper.
- **Unchanged:** all adapters, `sessions.py`, `orchestrator.py`, the parser,
  and the `login` / `status` commands and the all-or-nothing precheck.

## Design

### Build loop

`parse` + `precheck` stay as they are. The `with sync_playwright()` moves to wrap
the **whole** loop instead of one iteration:

```
with sync_playwright() as p:                 # one for the whole run
    contexts = []
    for platform in platforms:
        ctx, page = open_context(p, client, platform, headless=False)
        contexts.append((platform, ctx))
        try:
            build_document(page, doc, images_dir)   # SEQUENTIAL
            print("Done — draft built. Review and publish manually.")
        except Exception as e:
            failures.append((platform, repr(e)))
            print("FAILED … (window left open)")
        # window is NOT closed
    print("All N windows open; nothing will close on its own.")
    _wait_until_all_closed(contexts)
return 1 if failures else 0
```

Builds run **sequentially**: paste relies on the real clipboard + window focus
(VC/Dzen/Habr), so concurrent builds would fight over focus. By the end of the
loop all N windows are open at once.

### `_wait_until_all_closed(contexts)` — the fix

Delete the per-platform `input(...)` + `except EOFError: time.sleep(15)` +
`ctx.close()` block entirely (that branch is what lost drafts). Replace with a
liveness poll:

```
while any context still has a live (non-closed) page:
    pump Playwright events ~0.5s on any live page (guarded by try/except)
# loop exits only when the user has closed EVERY window → return
```

Properties:

- The script never calls `ctx.close()`; windows close only by user action.
- No `input()` → **EOF / non-TTY no longer breaks anything**; the pipeline/skill
  case waits for window close exactly like the terminal case.
- Close order is arbitrary — detection is by polling `page.is_closed()` across
  `ctx.pages`, not one-shot events (a past `close` event won't satisfy a later
  `wait_for_event`).
- `Ctrl+C` exits and lets Playwright tear down (an intentional interruption).

> Implementation note: the exact "pump events while waiting" idiom must be
> verified against Playwright's sync API during TDD. The poll guards every
> Playwright call so a window closing mid-poll is treated as closed, not an error.

### Error handling

A failing platform leaves its window open, records the failure, and the loop
continues. The failure summary prints **after** all windows close; exit code is
`1` if any platform failed, else `0`.

## Testing

Mirror `tests/test_orchestrator.py` (pure functions + injected fakes, no real
browser). Extract `_wait_until_all_closed` so it accepts a list of
context-like objects, then test with fakes:

- **fake context** exposes `.pages`, each page a fake whose `is_closed()` flips
  to `True` after N polls; `wait_for_timeout` is a no-op.
- Assertions: (a) does not return while any window is open; (b) returns once all
  are closed; (c) survives an exception raised by a window that closed mid-poll.

## Backlog (separate future design)

**One shared Chrome profile per client** (`.profiles/<client>/`) so every
platform is a **tab in one window**. Requires migrating the per-platform profile
model and re-logging into every platform (including the Habr/Dzen captcha manual
login). Tracked as future work; not in this change.

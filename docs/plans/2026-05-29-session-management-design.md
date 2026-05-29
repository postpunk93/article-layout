# Session management — design

**Date:** 2026-05-29
**Status:** approved (brainstorm), ready for implementation plan

## Goal

Flexible storage of multiple accounts so that, from a Claude session, the user can
say "lay out article X for client Y on platforms 1, 2, 3" and have it run. The
system must detect dead browser sessions and prompt for login when needed.

Today each adapter hardcodes a single profile dir (`.vc-profile`, `.pikabu-profile`)
— one account per platform — and "logged in?" is implicit (the editor selector
either appears or the wait raises). This design generalises to many accounts and
makes session liveness explicit.

## Decisions (from brainstorm)

- **Account model:** profile = `(client, platform)`. Matrix is sparse — some clients
  have 1 platform, some have 3.
- **Adding an account:** "add platform X for client Y" → create the profile folder if
  the client/account is new → open a visible browser → log in by hand → done.
- **Source of truth = folders.** A folder `(client, platform)` existing *is* the fact
  that the account is set up. No central registry file.
- **Metadata = `meta.json` inside each profile folder.** Travels with the profile;
  deleting the folder deletes everything; no drift. (Rejected a central SQLite/JSON
  registry: a second source of truth and drift risk, overkill at this scale.)
- **Layout never logs in.** Login is always a separate, explicit, human step done in
  advance. Liveness is never cached — every check probes the live site (cookies can
  expire server-side at any time).
- **Multi-platform run is all-or-nothing:** check every requested session first; if
  any is dead, lay out *nothing*, report who to log in.

## Architecture

### On-disk layout (all under one gitignored dir)

```
.profiles/
  <client>/
    vc/         persistent Chromium context (formerly .vc-profile) + meta.json
    pikabu/     persistent Chromium context (formerly .pikabu-profile) + meta.json
```

- `<client>/<platform>/` exists ⇒ account is set up.
- Clients = `ls .profiles/`; a client's platforms = `ls .profiles/<client>/`.
- `meta.json`: `{ "label": "ACME Corp", "login": "...", "notes": "...",
  "last_login_at": "2026-05-29" }`. Written by `login`, read by `status`. No liveness.

### Platform registry (in code, `src/sessions.py`)

```
PLATFORMS = {
  "vc":     { adapter: vc_adapter,     editor_url, alive_marker },
  "pikabu": { adapter: pikabu_adapter, editor_url, alive_marker },
}
```

`alive_marker` is a selector present in the editor **only when logged in**
(VC: the title selector; Pikabu: `.tiptap.ProseMirror`). Adding a future platform =
one entry here + the adapter.

### `src/sessions.py` — single owner of all profile logic

```
profile_dir(client, platform) -> Path           # .profiles/<client>/<platform>
list_clients() -> [str]
list_accounts(client) -> [platform]
open_context(p, client, platform, headless)      # launch_persistent_context on the dir
is_alive(client, platform) -> bool                # liveness probe (below)
read_meta / write_meta(client, platform, dict)    # meta.json beside the context
```

**Liveness probe (`is_alive`):** open the context **headless**, `goto(editor_url)`,
wait for `alive_marker` with a short timeout (~8s). Marker appears → alive. Login
redirect / marker absent → dead. Close the context. No cache. `headless=False` flag
available for debugging if a site behaves differently headless.

### Adapter refactor (minimal)

- `build_document(page, doc, images_dir)` is already pure — untouched.
- Remove the module-level `PROFILE_DIR` constant and the `run_document` wrapper that
  created its own context. Context creation moves into `sessions.open_context`.
- Adapter contract becomes: "give me a `page`, I build the draft." The `PLATFORMS`
  registry wires platform key → `build_document` + `editor_url` + `alive_marker`.

### Unified CLI — `python cli.py <command>`

| Command | Behaviour |
|---|---|
| `login <client> <platform>` | `open_context(headless=False)` → `goto(editor_url)` → wait for `alive_marker` or Enter → write `last_login_at` to meta. Interactive; user runs via `! python cli.py login ...`. |
| `status [client]` | For each pair, `is_alive` → table `client · platform · alive/dead` (+ meta label). |
| `layout <slug> <client> <platforms>` | Parse `in/<slug>/index.html` → `is_alive` on **all** requested platforms → if any dead: print `DEAD: client/platform`, exit non-zero, lay out nothing → else, per platform: `open_context(headful)` + `build_document`, leave windows open for manual publishing. `<platforms>` = `vc,pikabu` or `all`. |

`run_vc.py` / `run_pikabu.py` / `login_pikabu.py` are removed (replaced by `cli.py`).

### Claude-session UX

User: "lay out lists-quotes for acme on vc and pikabu" → I run
`python cli.py layout lists-quotes acme vc,pikabu`. If it reports `DEAD: acme/pikabu`,
I suggest `! python cli.py login acme pikabu`; user logs in; I re-run layout.

## Error handling

- Missing profile folder `(client, platform)` → treat as "needs login" (no stack
  trace), suggest `login`.
- Unknown client / platform / slug → clear message + list of available options.
- `build_document` fails mid-layout for one platform → caught; print which platforms
  succeeded / failed; leave windows open (current behaviour).

## Migration

- Move existing `.vc-profile` → `.profiles/default/vc` and `.pikabu-profile` →
  `.profiles/default/pikabu` (client `default`) to preserve current logins.
- `.gitignore`: replace `.vc-profile/` and `.pikabu-profile/` with `.profiles/`.

## Testing

Unit tests (no browser):
- `profile_dir` builds the correct path.
- `list_clients` / `list_accounts` read a tmp folder tree.
- `layout` arg parsing, including `platforms=all`.
- `meta.json` read/write round-trip.
- All-or-nothing pre-check with `is_alive` mocked: one dead ⇒ nothing laid out, exit
  code ≠ 0.

Browser paths (`open_context`, `is_alive`, `build_document`) stay under manual /
`verify` checks, as the adapters already are (52 unit tests + `verify_adapter.py`).

# Pikabu Browser Automation — Design

**Date:** 2026-05-29
**Status:** approved by user, ready to plan
**Builds on:** `2026-05-29-vc-browser-automation-design.md` (same parser + IR, new adapter)

## Why

User already transfers articles to VC via a Playwright adapter over a shared,
platform-agnostic IR. Pikabu is the next platform — and by design it is just a
**new adapter** reading the same IR. The parser, IR (`Heading / Paragraph /
Image / ListBlock / Quote` + a separate `title` field), and `emit_html` are
reused unchanged. "Work the same way as VC."

## Goal

Take a standard unpacked Google Docs zip (`in/<slug>/index.html` + `images/`)
and, via a Python + Playwright script, transfer it into the Pikabu post editor.
Where the script stops (saved draft vs. just-before-publish) is decided during
discovery, once we know whether Pikabu has drafts and what fields it requires.

## Data flow

```
in/<slug>/  →  parser.py (existing)  →  IR (existing)  →  pikabu_adapter.py (new)  →  post/draft in Pikabu
```

Layers 1–2 are reused without changes. Only layer 3 is new.

## Fixed decisions

| Decision | Choice |
|---|---|
| Auth | Saved browser profile (`./.pikabu-profile`, gitignored). User logs in by hand once; cookies persist. No password stored. |
| Stack | Python + Playwright (automation); parsing reuses the existing BeautifulSoup parser. |
| Run mode | Visible (headed) browser. Stops at a point determined during discovery; user does the final publish. |
| v1 block scope | Full VC set: h2 headings, paragraphs, bold/italic, images with captions, lists (ordered/unordered), quotes. **Degrade** any block Pikabu can't represent (rules fixed during discovery). |
| Code organization | Standalone `pikabu_adapter.py` (approach A). Copy `_type_runs` and the `build_document` dispatch skeleton from VC; write Pikabu-specific `_insert_*` fresh. No shared adapter base until a 3rd platform (rule of three). |
| Stop point + required fields (tags/community/flags) | Deferred to discovery. |

## Discovery phase (done first, with the user)

`src/discover_pikabu.py` opens the persistent browser on the new-post page and
**pauses**. With the user's help, verify against a checklist and record into
`experiments/04-pikabu-editor/notes.md`:

1. **URL** of the new-post page and how to detect a saved draft / published post.
2. **Selectors:** title field, body container, image-insert control, hidden
   `<input type=file>`.
3. **Which blocks the editor actually supports** — headings? lists (ordered?)?
   quotes? Fix the **degradation rules** here (ordered list → unordered or
   "1. "-prefixed text; subheading → bold paragraph; quote → ?).
4. **Inline formatting:** do Ctrl+B / Ctrl+I work, or is bold/italic applied
   another way (or unsupported)?
5. **Images:** upload via the file input; confirm a real image block appears;
   find where the caption is entered.
6. **Required fields** (tags / community / flags) and whether drafts exist —
   **this decides the stop point.**

Only after a filled `notes.md` is the adapter written.

## Adapter `pikabu_adapter.py` (approach A)

- `launch_persistent_context(user_data_dir="./.pikabu-profile", headless=False)`
  — visible window, session in the profile folder. First run: pause for manual
  login, then continue; cookies reused afterward.
- Own copy of `_type_runs()` (bold/italic via Ctrl+B / Ctrl+I) and the
  `build_document()` dispatch loop, mirroring the VC adapter.
- Pikabu-specific `_insert_*` functions, written against discovery facts.
- **Fail loudly:** on any unexpected state (selector missing, not logged in,
  image not uploaded) — pause with a clear console message; window stays open.
  No silent skips.
- Validate images: marker/image count in IR must equal files in `images/`, else
  stop with a warning.
- Never publishes on its own unless discovery shows that's the only viable stop;
  stop point set by discovery results.

## Entry point

`run_pikabu.py in/<slug>` — mirror of `run_vc.py`. Parse → build IR → run the
adapter.

## New files

```
src/discover_pikabu.py                  # discovery (pause + checklist)
src/pikabu_adapter.py                   # Playwright Pikabu automation
run_pikabu.py                           # entry point: python run_pikabu.py in/<slug>
experiments/04-pikabu-editor/notes.md   # discovery result
.pikabu-profile/                        # persistent profile (gitignored)
```

Parser, IR, `emit_html`, and parser tests are unchanged.

## Testing & validation loop

- Parser is already unit-tested — not touched.
- Adapter verified manually via the project's validation loop: one run →
  inspect the Pikabu result → **one change at a time** → repeat until clean.
  Stabilize across 2–3 articles.

## Boundaries of v1 (YAGNI)

- Pikabu only. Full VC block set, degrading unsupported blocks (rules fixed at
  discovery).
- No API posting, no unified CLI wrapper, no shared adapter base (extract only
  when a 3rd platform arrives).

## Prerequisites

- A logged-in Pikabu account (log in by hand on the first discovery run).
- A test article in `in/<slug>/` — can reuse `example/lists-quotes` (has lists,
  quotes, images) or a real article.

## Open questions (do not block start)

- Exact Pikabu selectors, paste/typing mechanism, supported blocks — resolved by
  discovery.
- Stop point and handling of tags/community/flags — resolved by discovery.
- Degradation rules for blocks Pikabu can't represent — resolved by discovery.

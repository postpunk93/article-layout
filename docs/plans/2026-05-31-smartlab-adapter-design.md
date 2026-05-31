# Smartlab adapter — design

Date: 2026-05-31
Branch: `feat/smartlab-adapter` (to be created from `main`)

Fourth platform adapter, alongside VC (Editor.js, clipboard paste), Pikabu
(Tiptap, HTML paste + File-paste images) and Habr (Tiptap, HTML paste +
auto-upload images). Lays out a GDoc-sourced article into smart-lab.ru's post
editor and stops at a draft/preview state for manual completion. Never publishes.

## Goal & scope (v1)

- Same coverage as the other adapters: title + body (headings, bold/italic,
  bullet/ordered lists, quotes, images with captions) from the shared IR.
- Drive the editor to a **draft / preview** state and **stop** — never publish
  automatically (consistent with VC/Pikabu/Habr).
- **Out of scope (backlog):** tags/topic selection, any publish step, cut markers.

## Key facts (confirmed with the user)

- **Editor type: UNKNOWN — discovery required.** The honest path (same as Habr):
  log in, open the post form, inspect the DOM, then pick the body strategy.
- **Auth: ordinary login/password**, account exists. Start with the **standard
  Playwright login flow** (like VC/Pikabu). Escalate to `manual_login` via
  system Chrome (like Habr) ONLY if discovery reveals a CDP-blanking captcha.
- **URLs (given by user):**
  - `ADD_URL  = "https://smart-lab.ru/topic/add/"` — post editor form
  - `LOGIN_URL = "https://smart-lab.ru/login/"` — login page
  - `HOME_URL = "https://smart-lab.ru/"`

## Approach (chosen: A — discovery-first, then mirror the closest adapter)

Considered:
- **A. Discovery-first, then mirror.** Add minimal `smartlab` registration so we
  can log in and open the editor; inspect the DOM; choose the body strategy;
  implement `build_document`. *Chosen* — editor is genuinely unknown and the
  project already proved this path works (Habr).
- **B. Assume Tiptap, reuse Habr's HTML-paste immediately.** Fast if modern, but
  a blind bet — full rewrite if it's a textarea/BBCode/CKEditor.
- **C. Treat as a markup/HTML source field.** Deterministic, but images still
  need a separate upload flow and it's brittle if the field rejects raw HTML.

The body strategy is finalized AFTER discovery, as one of:
1. **HTML-paste + post-passes** (Habr/Pikabu path) — if a modern contenteditable
   editor that keeps high-fidelity paste.
2. **Clipboard-paste + restore passes** (VC path) — if paste is lossy.
3. **Markup/HTML generation into the field** — if a textarea / BBCode / source mode.

All three reuse `emit_html.emit_body` via its existing flags
(`caption_marker`, `quote_as_paragraph`, `img_sep`, `max_heading_level`,
`image_src`). No new IR; no edits to shared modules.

## Architecture

Sits on top of the existing two-layer scheme without changing any contracts:

- **Deterministic layer (written first, by analogy with `habr_adapter`):** new
  module `src/smartlab_adapter.py` with constants (`HOME_URL`, `LOGIN_URL`,
  `ADD_URL`, `BODY_SEL`, `TITLE_SEL`, `ALIVE_SEL`) and
  `build_document(page, doc, images_dir, log=print)`. Registered in
  `sessions.PLATFORMS["smartlab"]`. `cli.py` and `orchestrator.py` need NO
  changes — `parse_platforms`/`precheck`/`cmd_layout` are already generic, so
  `smartlab` is automatically included in `all`.
- **Login:** standard Playwright flow by default (no `manual_login` key). If
  discovery finds a captcha, add `"manual_login": True` + `"login_url"` like
  Habr — the plumbing already exists.
- **Discovery layer (phase before `build_document`):** open the post form with a
  live browser, inspect the editor DOM, record findings in
  `docs/platform-notes.md` (new "Smartlab" section).

Principle: **no new IR, no edits to shared modules.** New code lives in one
adapter file (+ one entry in `PLATFORMS`).

## Components & discovery protocol

**Deterministic skeleton `src/smartlab_adapter.py`** (constants + functions,
modeled on `habr_adapter`):

- `HOME_URL`, `LOGIN_URL`, `ADD_URL` — URLs (above).
- `ALIVE_SEL` — a logged-in-only marker (a "write" link/menu item or the editor
  body itself).
- `BODY_SEL`, `TITLE_SEL` — body and title selectors (confirmed at discovery).
- `build_document(page, doc, images_dir, log=print)` — skeleton: open form →
  type title → insert/generate body → upload images → post-passes (quotes /
  captions if no native ones) → reach preview/draft and **stop**.
- Private helpers as needed (`_paste_html`, `_data_uri`,
  `_wait_for_image_uploads`, `_convert_quotes`, `_set_captions`) — reuse/copy
  from Habr only those that fit the discovered engine.

**Discovery protocol — what we determine and record in `platform-notes.md`:**

1. **Editor type** — Tiptap/ProseMirror? CKEditor/TinyMCE? raw textarea?
   BBCode/Markdown? (DOM classes, `contenteditable`, iframe presence).
2. **Title** — separate field, or first node of the body.
3. **Paste behavior** — does `paste` keep HTML (bold/italic/lists/headings), or
   is it flat → need the clipboard path / markup generation.
4. **Images** — auto-upload from data-URI (like Habr)? a button / `<input
   type=file>`? a separate upload endpoint? is there a native caption field.
5. **Quotes / captions** — native quote and image-caption fields, or emulate
   with markers.
6. **Stop button** — "Предпросмотр" / "Сохранить черновик" / "Далее" — where it
   is safe to stop without publishing.
7. **Login captcha** — present or not (decides escalation to `manual_login`).

Discovery results update this design (or a short follow-up note) before
`build_document` is finalized.

## Data flow

```
in/<slug>/index.html  --parse()-->  Document (IR: Heading/Paragraph/List/Quote/Image+caption)
                                          |
cli.py layout <slug> <client> smartlab    |
   |- orchestrator.precheck (all-or-nothing) --> sessions.is_alive("smartlab")
                                          |   (opens ADD_URL, waits for ALIVE_SEL)
                                          v
   sessions.open_context (installed Chrome, profile .profiles/<client>/smartlab/)
                                          v
   smartlab_adapter.build_document(page, doc, images_dir, log):
        1. goto ADD_URL, wait for BODY_SEL
        2. type doc.title into TITLE_SEL
        3. BODY: emit_html.emit_body(doc, <flags per engine>) --> paste/generate
        4. images: data-URI auto-upload OR <input type=file> (per discovery)
        5. post-passes: quotes, captions (if no native ones)
        6. stop at preview/draft — do NOT publish
```

Same end-to-end flow as VC/Pikabu/Habr. Only layer 3 (how the body enters the
editor) and step 4 (images) are fixed by discovery.

## Error handling

- **All-or-nothing at the gate:** `precheck` already ensures a dead `smartlab`
  session (or any requested platform) lays out NOTHING and reports who to log in.
- **Liveness, no cache:** `is_alive` re-opens `ADD_URL` and waits for `ALIVE_SEL`
  every time; missing profile = dead.
- **Platform-failure isolation:** `cmd_layout` already wraps `build_document` in
  try/except, collects failures, leaves the window open, continues to the next
  platform.
- **Best-effort inside `build_document`** (like Habr): image-upload wait has a
  timeout and is logged on failure but does not abort; each quote/caption is
  converted in its own try/except with a `log(...)`.
- **Safe stop:** the "reach preview/draft" click is wrapped in try/except — if
  the button is not found, log "advance manually" and leave the window open
  (like Habr's «Далее к настройкам»). Publishing is never touched.
- **Login escalation:** if discovery finds a captcha, add `manual_login`; until
  then, standard flow.

## Testing

Unit-test the pure/deterministic logic; validate the browser part manually
end-to-end (the project's established line for all adapters).

**Automated (pytest), no browser:**
- `tests/test_sessions_registry.py` — extend: `smartlab` is in
  `known_platforms()`, its `PLATFORMS` entry has `build_document`, `editor_url`,
  `alive_marker`, and it appears in `parse_platforms("all", ...)`.
- If discovery introduces new `emit_body` behavior (e.g. a BBCode flag / special
  separator), add a focused test in `tests/test_emit_html.py`. If we reuse
  existing flags, no new emit tests are needed.
- Any pure helper that appears (e.g. markup formatting) is covered like
  `test_vc_format_segments.py`.

**Manual validation (acceptance), like the others:**
- `python cli.py login <client> smartlab` → log in, session saved.
- `python cli.py status` → `smartlab` = `alive`.
- `python cli.py layout <slug> <client> smartlab` on a real article from `in/` →
  verify in preview/draft: title, bold/italic, lists, quotes, images with
  captions — and that **nothing is published**.

**Not auto-tested:** smart-lab DOM selectors and paste behavior — validated by
live run and recorded in `platform-notes.md` (brittle to site changes; mocking
is pointless).

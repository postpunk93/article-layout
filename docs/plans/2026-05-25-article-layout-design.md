# Article Layout — Design (Phase 1)

**Date:** 2026-05-25
**Status:** approved by user, ready to execute

## Problem

User publishes the same article on **Habr**, **VC.ru**, and **Smartlab**. Drafts live in Google Docs. Today the transfer is: download GDoc → open in browser → copy-paste into each platform's editor. This loses:

- **Images** — relative paths in clipboard HTML don't resolve in the target editor.
- **Captions** — in GDoc, the line under an image is plain text; in the target it should be an image caption block.
- **Quotes** — in GDoc, quotes are paragraphs with a yellow background; in the target they should be `<blockquote>` blocks.
- **General formatting** — extra Google styles leak in; headers, bold/italic, lists drift.
- **Platform adaptation** — each platform has its own block types and rules.

## Goal of Phase 1

Find a reliable way to paste a Google-Docs-exported article into **VC.ru's editor only**, with images and semantic blocks intact, using **manual copy-paste**.

Once VC works, repeat for Habr and Smartlab in later phases.

## Out of scope (Phase 1)

| Deferred | Re-evaluate when |
|---|---|
| Habr, Smartlab | VC stable on 3 articles in a row |
| API-based posting | Manual paste becomes the bottleneck |
| GDoc fetch via Google Drive MCP | Manual folder-download becomes the bottleneck |
| CLI tool, package, web UI, browser extension | Tool runs more than once a week |
| Lists, tables, code blocks, embeds | First article that uses them |
| Tests, CI, linters | After Step 6 of the validation loop (codification) |
| Yellow-background quote recognition | First article with quotes appears |
| Stack choice for the converter | After image transport is solved |

## Input contract

User downloads a Google Doc as **"Web page (.html, zipped)"** and unzips into `in/<slug>/`. The folder always contains:

```
in/<slug>/
├── index.html      # single-file GDoc HTML export
└── images/
    └── imageN.png  # 1..N
```

The reference example (`example/`) was inspected. Observations about this format are pinned in user memory (`project_article_layout.md`). Key points:

- Body is a flat sequence of `<h1>`, `<h2>`, `<p>`. **No** `<figure>`, `<figcaption>`, `<blockquote>`, `<ul>`, `<ol>`, `<li>` — even when the source visually uses them.
- All styling lives in inline `<style>` and class names `.c0..cN`.
- Text inside `<p>` is fragmented across many `<span>` elements (e.g., the H1 "170" splits as "1" / "7" / "0").
- Image-with-caption pattern: `<p><img src="images/imageN.png"><br>Caption text</p>`. Standalone image: `<p><img...></p>`.
- Highlight classes (`.c7` light-blue, `.c11` pink) declared but unused in the example. User confirmed they highlight quotes in **yellow** — likely a third color class will appear in a quote-containing article.

## Project structure

```
C:\Projects\article-layout\
├── example\                       # reference input — do not modify
│   ├── index.html
│   └── images\
├── in\                            # new articles dropped here
│   └── <slug>\
│       ├── index.html
│       └── images\
├── out\                           # generated outputs (per article, per platform)
│   └── <slug>\
│       └── vc\
│           ├── attempt-1.html     # open in browser, copy, paste into VC
│           ├── attempt-N.html
│           └── notes.md           # what was tested, what broke, what changed
├── experiments\                   # image-transport experiments (Phase 1a)
│   └── 0N-<name>\
│       ├── test.html
│       └── notes.md
├── src\                           # converter code (added at Step 6 of validation loop)
├── docs\
│   └── plans\
│       └── 2026-05-25-article-layout-design.md  # this file
```

## Phase 1a — Image-transport experiment (priority)

**Risk hypothesis:** the entire "manual paste" approach hinges on images being transferable through the OS clipboard. The user has already confirmed that pasting from a browser-opened `index.html` does **not** carry images into VC. We must validate a transport before designing anything else.

**Experiment plan, in order:**

1. **Data URI** — single `<img src="data:image/png;base64,…">` inlined in a minimal HTML file. Open locally, copy, paste into a fresh VC draft.
2. **Local HTTP server** — same HTML but served from `python -m http.server` so the browser context is `http://localhost:…` instead of `file://`.
3. **Public URL** — image uploaded to a public host; HTML uses absolute `https://…`.
4. **Structure-only fallback** — HTML without images, with `[IMAGE-N]` placeholders. User drags image files from `images/` into the editor manually at each placeholder.

**Stop condition:** the first hypothesis where the image appears as a real image block in the VC draft after a single paste. Record findings in `experiments/0N-*/notes.md`.

Each experiment uses **one** image from `example/images/image5.png` ("Это я"), surrounded by a heading and two paragraphs for context. No converter code yet — these are hand-built HTML files.

## Phase 1b — Conversion rules (apply once image transport is known)

The converter reads `in/<slug>/index.html` and emits `out/<slug>/vc/attempt-1.html` using the rules below. Implementation language deferred to after Phase 1a.

**Cleanup:**

- Drop `<head>`, `<style>`, inline `.cN` class attributes.
- Decode HTML entities.
- Merge adjacent `<span>` elements with the same effective style.
- Remove empty `<p>` / `<p><span></span></p>`.

**Semantic mapping:**

| Source pattern in GDoc HTML | Target block |
|---|---|
| `<h1>` | `<h1>` (article title) |
| `<h2>` | `<h2>` (section header) |
| `<p>` with plain text | `<p>` |
| `<p><img><br>Text</p>` | `<figure><img><figcaption>Text</figcaption></figure>` |
| `<p><img></p>` (no `<br>` and no following text) | `<figure><img></figure>` |
| `<span>` with `font-style: italic` | `<em>` |
| `<span>` with `font-weight: 700` | `<strong>` |
| `<p>` where the entire text is highlighted (yellow / blue / pink background) | `<blockquote>` *(deferred until we see a real article with highlights)* |
| `<a href="https://www.google.com/url?q=…">` | `<a href="…">` (unwrap Google's link wrapper) |
| Lists, tables, code, embeds | not implemented in Phase 1 |

Image `src` substitution depends on the transport chosen in Phase 1a.

## Validation loop

For each article, after Phase 1a is settled:

1. Generate `attempt-1.html` (manually at first; via script once rules stabilize).
2. User opens in browser, copies, pastes into a fresh VC draft, screenshots, lists deltas in `notes.md`.
3. Apply one change at a time → `attempt-N+1.html`. Never bundle multiple fixes — we'd lose causality.
4. Repeat until paste is clean.
5. After 2–3 articles converge without changes, **codify**: port the manual logic into a script in `src/`.

Switch to Habr (then Smartlab) only after VC is stable.

## Open questions (do not block start)

- Which highlight color(s) map to which semantic block. Resolved when the first quote-containing article arrives.
- Final converter stack (Python, Node, something else). Resolved at codification step.
- Whether VC has a quirk requiring different HTML when pasted from `file://` vs `http://localhost` vs `https://…`. Will surface during Phase 1a experiments.

## Immediate next step

Build `experiments/01-data-uri/test.html` using `example/images/image5.png` and a tiny surrounding skeleton. User pastes into a fresh VC draft and reports.

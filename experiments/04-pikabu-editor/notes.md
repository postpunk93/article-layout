# Experiment 04 — Pikabu editor discovery

**Date:** <fill>
**Goal:** record real selectors, the working text-insert mechanism, the set of
supported blocks (+ degradation rules), and the stop point — before writing the
adapter.

## New-post navigation
- URL of the "new post" page: <fill>
- How to detect logged-out state (selector/text): <fill>
- Is there a draft concept? How is a saved draft detected (URL / toast / indicator): <fill>

## Selectors
- Title field: <fill>
- Body editor container (contenteditable / textarea / block editor?): <fill>
- Image-insert control (button / "+" / drag zone): <fill>
- Hidden file input for image upload: <fill>
- Caption field on an inserted image block (if any): <fill>

## Supported blocks + degradation rules (we bring the full VC set)
- Headings (H2)? supported / NO -> degrade to: <fill, e.g. bold paragraph>
- Bold / italic inline? supported via Ctrl+B / Ctrl+I / other / NO: <fill>
- Unordered list? supported / NO -> degrade to: <fill>
- Ordered list? supported / NO -> degrade to: <fill, e.g. "1. " text prefix>
- Quote / blockquote? supported / NO -> degrade to: <fill>
- Image caption? supported / NO -> degrade to: <fill, e.g. italic paragraph under image>

## Text-insert mechanism (pick the one that works)
- [ ] per-block typing via keyboard (like VC adapter): type runs, Enter between blocks
- [ ] paste clean HTML (emit_html.emit_body) via clipboard + Ctrl+V
- [ ] paste via dispatched `paste` event with DataTransfer(text/html)
- Notes on what survives a paste (h2, bold, em, lists): <fill>

## Image upload
- After set_input_files on the file input, does a real image block appear? <fill>
- Is upload async (must wait for the <img> to finish loading, like VC)? <fill>
- Where/how is the caption entered for that block (if supported)? <fill>

## Required fields + stop point  (RESOLVES design open question)
- Tags: required? where/how entered? <fill>
- Community / section: required? how chosen? <fill>
- Flags (18+, authored, etc.): required? <fill>
- DECISION — where the adapter stops: <draft saved | filled up to before "Publish" | other>
- DECISION — which required fields (if any) the adapter fills vs. leaves to the user: <fill>

# Experiment 03 — VC editor discovery

**Date:** <fill>
**Goal:** record real selectors + the working paste mechanism before writing the adapter.

## New-entry navigation
- URL of the "write new entry" page: <fill>
- How to detect logged-out state (selector/text): <fill>
- How to detect a saved draft (URL change / toast / autosave indicator): <fill>

## Selectors
- Title field: <fill>
- Body editor container (contenteditable): <fill>
- Image-insert control ("+" / toolbar button): <fill>
- Hidden file input for image upload: <fill>
- Caption field on an inserted image block: <fill>

## Text paste mechanism (pick the one that works)
- [ ] clipboard write via context.grant_permissions(["clipboard-write"]) + Ctrl+V
- [ ] dispatch a `paste` event with DataTransfer(text/html)
- Notes on what survived (h2, bold, em): <fill>

## Markers
- Do `[[IMG:...]]` / `[[CAP:...]]` markers survive the paste verbatim? <fill>
- Can the cursor be placed on a marker to replace it? <fill>
- If markers are unreliable -> fall back to per-block typing (variant A). Decision: <fill>

## Image upload
- After set_input_files on the file input, does a real image block appear? <fill>
- Where/how is the caption entered for that block? <fill>

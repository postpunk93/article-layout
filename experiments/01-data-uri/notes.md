# Experiment 01 — Data URI

**Date:** 2026-05-25
**Source:** `experiments/01-data-uri/test.html` (heading + 2 paragraphs + figure with data-URI image + figcaption)
**Image:** `example/images/image5.png` (676 KB raw → 901 KB base64)

## Result

- Heading: ✅ kept
- Paragraphs: ✅ kept
- Image: ❌ dropped — VC's paste handler strips `data:` URIs
- Caption: ✅ attached correctly (i.e. the *figure/figcaption* structure was preserved; the image slot was just empty)

## Verdict

- [x] FAIL — data URIs are not a viable transport for VC. Proceed to experiment 02 (localhost).

## Takeaway

Structure (h1, p, figure, figcaption) DOES survive paste — that's a useful side finding for the future converter. Only the image bytes were lost. Confirms the problem is purely the image *src* scheme, not the surrounding markup.

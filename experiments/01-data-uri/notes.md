# Experiment 01 — Data URI

**Date:** 2026-05-25
**Source:** `experiments/01-data-uri/test.html` (heading + 2 paragraphs + figure with data-URI image + figcaption)
**Image:** `example/images/image5.png` (676 KB raw → 901 KB base64)

## Result

- Heading: <kept as H1 / merged into paragraph / lost>
- Paragraphs: <kept / merged / split>
- Image: <appeared as image block / appeared as broken icon / silently dropped / something else>
- Caption: <attached to image as caption / orphaned paragraph below / lost>

## Screenshot

(attach or describe)

## Verdict

- [ ] PASS — image lands as a real image block. Stop here. Data URI is our strategy.
- [ ] FAIL — proceed to Task 2 (experiment 02).

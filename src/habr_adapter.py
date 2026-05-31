"""Drive Habr's visual article editor to build a draft from a Document.

WORK IN PROGRESS. For now this only provides the constants `cli.py login/status`
need to target Habr; `build_document` is a stub until the discovery probe (Task 2)
confirms the editor selectors and paste mechanics. See the plan at
docs/plans/2026-05-31-habr-adapter.md and the design at
docs/plans/2026-05-31-habr-adapter-design.md.

Planned behavior: high-fidelity HTML paste of the body (Pikabu model), h3+ headings
degraded to a bold line (emit max_heading_level=2), post-passes for quotes and image
captions, then advance to the article-settings screen and STOP (never publish).
"""

# Sandbox article editor. Provisional — the discovery probe confirms the exact URL.
EDITOR_URL = "https://habr.com/ru/sandbox/add/"

# Provisional selectors — replaced by the discovery probe (Task 2). Only ALIVE_SEL
# is consumed so far (by status/is_alive); the real value comes from discovery.
TITLE_SEL = "textarea[placeholder]"
BODY_SEL = "[contenteditable='true']"
ALIVE_SEL = TITLE_SEL


def build_document(page, doc, images_dir):
    raise NotImplementedError(
        "Habr build_document is not implemented yet — pending the discovery probe "
        "(Task 2 in docs/plans/2026-05-31-habr-adapter.md)."
    )

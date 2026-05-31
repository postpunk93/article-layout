"""Drive Yandex Dzen's article editor (Draft.js) to build an autosaved draft.

See docs/plans/2026-05-31-dzen-adapter-design.md. Dzen attaches to a LIVE Chrome
via connect_over_cdp (the master Yandex SSO cookie is session-scoped, so the
Habr "login then reopen profile" scheme bounces to passport). One real clipboard
paste carries headings/paragraphs/bold/italic/quotes/lists natively; only images
need a native-upload pass; stop at autosave, never publish.
"""
import time
from pathlib import Path

from src.emit_html import emit_body
from src.ir import Image

# Studio dashboard; /profile/editor/create redirects here when logged in.
STUDIO_URL = "https://dzen.ru/profile/editor/create"
DEBUG_PORT = 9222

ADD_PUBLICATION_SEL = '[data-testid="add-publication-button"]'   # the "+" in the studio header
BODY_SEL = '.public-DraftEditor-content[spellcheck="true"]'      # body contenteditable (title is spellcheck=false)
TITLE_SEL = '.public-DraftEditor-content[spellcheck="false"]'    # title contenteditable
STATUS_SEL = '[class*="editor-header__status"]'                  # autosave indicator
SIDE_BUTTON_SEL = '[class*="side-button__sideButton"]'           # reveal-on-hover image "+"
IMAGE_FILE_INPUT_SEL = 'input[type=file][class*="image-popup__file"]'
FIGCAPTION_SEL = 'figure.zen-editor-block-image figcaption'
# Logged-in marker: the studio "+" only renders for an authenticated user.
ALIVE_SEL = ADD_PUBLICATION_SEL


def body_html(doc):
    """Clean body HTML for the paste: real <blockquote> (Dzen makes a native quote
    block), images as [[IMG:file]] markers (data-URIs error in Dzen), captions set
    natively (no marker)."""
    return emit_body(doc, caption_marker=False, quote_as_paragraph=False, img_sep=":")


def _open_editor(page, log):
    """From a logged-in live session, open a fresh article editor and return when the
    body contenteditable is present."""
    if "/edit" in page.url:
        try:
            page.wait_for_selector(BODY_SEL, timeout=4000)
            return
        except Exception:  # noqa: BLE001
            pass
    log("Opening Dzen studio…")
    page.goto(STUDIO_URL, wait_until="domcontentloaded")
    page.wait_for_selector(ADD_PUBLICATION_SEL, timeout=30000)  # logged-in marker
    page.locator(ADD_PUBLICATION_SEL).first.click()
    page.wait_for_timeout(800)
    for item in ["text=Написать статью", "text=Статья"]:
        loc = page.locator(item)
        if loc.count():
            loc.first.click()
            break
    page.wait_for_selector(BODY_SEL, timeout=20000)
    log(f"Article editor: {page.url}")


def build_document(page, doc, images_dir, log=print):
    raise NotImplementedError("dzen build_document is finalized in a later unit (browser methods)")

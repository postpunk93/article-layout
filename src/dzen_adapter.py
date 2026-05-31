"""Drive Yandex Dzen's article editor (Draft.js) to build an autosaved draft.

See docs/plans/2026-05-31-dzen-adapter-design.md. Dzen attaches to a LIVE Chrome
via connect_over_cdp (the master Yandex SSO cookie is session-scoped, so the
Habr "login then reopen profile" scheme bounces to passport). One real clipboard
paste carries headings/paragraphs/bold/italic/quotes/lists natively; only images
need a native-upload pass; stop at autosave, never publish.
"""
from pathlib import Path

from src.emit_html import emit_body

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


def build_document(page, doc, images_dir, log=print):
    raise NotImplementedError  # filled in by later tasks

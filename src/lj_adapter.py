"""Drive LiveJournal's new post editor (Draft.js) to build an autosaved draft.

See docs/plans/2026-06-02-lj-adapter-design.md. The body editor is Draft.js (like
Dzen): one real clipboard paste of clean HTML carries headings/paragraphs/bold/
italic/quotes/lists; only images need a native-upload pass; stop at autosave, never
publish.
"""
import time
from pathlib import Path

from src.emit_html import emit_body
from src.ir import Image

POST_URL = "https://www.livejournal.com/post/"
BODY_SEL = '.public-DraftEditor-content[contenteditable="true"]'
TITLE_SEL = "textarea.js--post-title"
PUBLISH_SEL = "button.js--toggle-submission-popup"   # NEVER click — publish flow
# Logged-in marker: the Draft.js body mounts only for an authenticated user.
ALIVE_SEL = BODY_SEL


def body_html(doc):
    """Clean body HTML for the paste: real <blockquote> (LJ makes a native quote
    block), images as [[IMG:file]] markers replaced after the paste."""
    return emit_body(doc, caption_marker=False, quote_as_paragraph=False, img_sep=":")

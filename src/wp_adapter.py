"""Drive the WordPress / Gutenberg editor (ruminlab.ru) to build a draft.

One real Ctrl+V of our clean body HTML produces native Gutenberg blocks
(headings, lists, quote, bold/italic) and auto-sideloads <img> data-URIs into
the media library. The canvas is in an iframe, but the wp.data store lives on
the TOP window, so the title, image captions, and "save draft" are driven via
wp.data — the iframe is touched only for the single body paste. Visible browser,
shared client profile, STOPS at a saved draft (never publishes).
"""
import base64
import mimetypes
import time
from pathlib import Path

from src.emit_html import emit_body

SITE = "https://ruminlab.ru"
EDITOR_URL = f"{SITE}/wp-admin/post-new.php"
ALIVE_SEL = ".editor-document-tools__inserter-toggle"
CANVAS_SEL = 'iframe[name="editor-canvas"]'


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def body_html(doc, images_dir: Path) -> str:
    """Clean Gutenberg-paste HTML: real <blockquote>, <img> as data-URIs (WP
    sideloads them to the media library on paste), and captions as [[CAP:text]]
    marker paragraphs that the post-paste cleanup pass moves into each image's
    native caption."""
    return emit_body(
        doc, quote_as_paragraph=False, caption_marker=True, img_sep=" ",
        image_src=lambda f: _data_uri(images_dir / f),
    )

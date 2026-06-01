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
    block), images as [[IMG:file]] markers replaced after the paste.

    Probe (a), verified live: a pasted <blockquote> becomes a native Draft.js
    <blockquote data-block="true"> quote block, and <ul>/<ol> become native
    list-item blocks — no post-paste convert pass is needed (unlike VC)."""
    return emit_body(doc, caption_marker=False, quote_as_paragraph=False, img_sep=":")


def _open_editor(page, log):
    """Open a fresh post editor, dismiss the restore-draft modal, return when the
    body contenteditable is present."""
    log("Opening LiveJournal post editor…")
    page.goto(POST_URL, wait_until="domcontentloaded")
    page.wait_for_selector(BODY_SEL, timeout=30000)  # logged-in marker
    page.wait_for_timeout(1200)
    # "Открыть последний черновик?" — start clean, decline restoring the old draft.
    for sel in ["text=Нет, спасибо", '[aria-label="Modal Window Close"]']:
        loc = page.locator(sel)
        if loc.count():
            log("Dismissing restore-draft modal.")
            loc.first.click()
            page.wait_for_timeout(600)
            break
    log(f"Editor ready: {page.url}")


def _set_clipboard(page, html):
    page.evaluate(
        """async (html) => {
            const plain = html.replace(/<[^>]+>/g, '');
            await navigator.clipboard.write([new ClipboardItem({
                'text/html': new Blob([html], {type: 'text/html'}),
                'text/plain': new Blob([plain], {type: 'text/plain'}),
            })]);
        }""",
        html,
    )


def _set_title_and_body(page, doc, log):
    log(f"Title: {doc.title!r}")
    page.fill(TITLE_SEL, doc.title)
    # A real Ctrl+V only pastes into a FOCUSED tab; bring it to the foreground.
    page.bring_to_front()
    html = body_html(doc)
    _set_clipboard(page, html)
    page.click(BODY_SEL)
    page.wait_for_timeout(300)
    page.keyboard.press("Control+V")
    page.wait_for_timeout(1500)
    log("Body pasted.")

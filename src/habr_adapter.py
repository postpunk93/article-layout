"""Drive Habr's visual article editor (Tiptap / ProseMirror) to build a draft.

Habr's editor is Tiptap — like Pikabu — so the whole body goes in as ONE
high-fidelity HTML paste (headings, bold/italic, bullet/ordered lists survive).
Two things make Habr the simplest target:
  * the TITLE is the first node of the editor doc (`.tiptap .title`, an <h1>);
  * an image pasted as <img src="data:…"> is AUTO-UPLOADED by Habr to
    habrastorage — no markers, no File paste; we just wait for the https src.

What paste does NOT do, and the post-passes that fix it:
  * <blockquote> lands as a plain paragraph -> convert via the per-block menu
    («Цитата», `button.right-menu__item`);
  * Habr has ONE subheading level, so the body is emitted with
    max_heading_level=2 (h3+ -> a bold line);
  * captions ride in the body and are moved into each image's caption field.

Then click «Далее к настройкам» and STOP on the settings screen (never publish).

Login vs automation: the login captcha blanks under CDP, so logging in uses a
hand-launched Chrome (see sessions.manual_login); automation reuses that session
via Playwright channel="chrome" (see sessions.open_context). Details in
docs/platform-notes.md ("Habr").
"""
import base64
import mimetypes
import time
from pathlib import Path

from src.emit_html import emit_body
from src.ir import Image

HOME_URL = "https://habr.com/ru/feed/"
LOGIN_URL = "https://habr.com/ru/auth/login/"
# The "write" pencil in the top navbar routes to the right editor for the account
# (sandbox or full); it renders only for a logged-in user, so it doubles as the
# liveness marker.
PENCIL_SEL = "a:has(svg.tm-header-user-menu__icon_write)"
ALIVE_SEL = PENCIL_SEL

BODY_SEL = ".tiptap.ProseMirror"
TITLE_SEL = ".tiptap .title"            # first node of the doc (<h1 class="title">)
BODY_PARA_SEL = ".tiptap .node_paragraph"  # first body block (after the title node)
SETTINGS_BUTTON_TEXT = "Далее к настройкам"


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def _paste_html(page, html):
    """Insert body HTML via a synthetic paste event (Tiptap keeps it high-fidelity)."""
    page.evaluate(
        """(html) => {
            const el = document.querySelector('.tiptap.ProseMirror');
            el.focus();
            const dt = new DataTransfer();
            dt.setData('text/html', html);
            dt.setData('text/plain', html.replace(/<[^>]+>/g, ''));
            el.dispatchEvent(new ClipboardEvent('paste',
                {clipboardData: dt, bubbles: true, cancelable: true}));
        }""",
        html,
    )


def _wait_for_image_uploads(page, expected, log, timeout=120000):
    """Wait until every pasted <img> has swapped its data-URI for an https CDN src.

    Habr fetches each pasted data-URI image and re-hosts it on habrastorage; the
    src flips from data: to https once done. Skipping this races later steps.
    """
    if expected <= 0:
        return
    try:
        page.wait_for_function(
            """(n) => {
                const imgs = [...document.querySelectorAll('.tiptap.ProseMirror img')];
                if (imgs.length < n) return false;
                return imgs.every(i => i.complete && i.naturalWidth > 0 &&
                                       /^https?:/.test(i.currentSrc || i.src || ''));
            }""",
            arg=expected,
            timeout=timeout,
        )
    except Exception as e:  # noqa: BLE001 — report, continue (best-effort)
        log(f"  image upload wait timed out ({str(e)[:80]})")


def build_document(page, doc, images_dir, log=print):
    images_dir = Path(images_dir)

    log(f"Opening editor via navbar pencil ({HOME_URL})")
    page.goto(HOME_URL, wait_until="domcontentloaded")
    page.locator(PENCIL_SEL).first.click()
    page.wait_for_selector(BODY_SEL, timeout=30000)
    time.sleep(2)

    log(f"Title: {doc.title!r}")
    page.click(TITLE_SEL)
    page.keyboard.type(doc.title)

    # Move the caret into the body BEFORE pasting — the title is the first node of
    # the same editor, so a paste while focused in the title lands in the title.
    page.click(BODY_PARA_SEL)

    # Whole body in one high-fidelity paste. Images are real <img> data-URIs that
    # Habr auto-uploads; h3+ degrade to a bold line (Habr has one subheading level).
    log("Pasting body HTML…")
    body_html = emit_body(
        doc, caption_marker=False, max_heading_level=2,
        image_src=lambda f: _data_uri(images_dir / f),
    )
    _paste_html(page, body_html)
    time.sleep(1.0)

    n_images = sum(1 for b in doc.blocks if isinstance(b, Image))
    log(f"Waiting for {n_images} image upload(s) to habrastorage…")
    _wait_for_image_uploads(page, n_images, log)

    # TODO (next passes): convert pasted quotes to native quote blocks; move image
    # captions into each image's native caption field.

    log(f"Advancing to settings: «{SETTINGS_BUTTON_TEXT}»")
    try:
        page.locator(f"button:has-text('{SETTINGS_BUTTON_TEXT}')").first.click(timeout=10000)
        log("On the settings screen. Stopping (fill hubs/audience/keywords and publish manually).")
    except Exception as e:  # noqa: BLE001
        log(f"Could not click «{SETTINGS_BUTTON_TEXT}» ({str(e)[:80]}); advance manually.")

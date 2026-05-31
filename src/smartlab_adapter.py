"""Drive smart-lab.ru's post editor to build a draft.

The editor is **TinyMCE 3.5.11** (discovery recorded in docs/platform-notes.md
"Smartlab"). The body goes in via the TinyMCE API
(`tinymce.get('topic_text').setContent(html)`), which renders our emitted HTML
natively (bold/italic, bullet/ordered lists, blockquote, headings). Then we
click «предпросмотр» (preview) and STOP — never «опубликовать» (publish).

Auth is an ordinary login/password (standard Playwright login flow).
"""
from pathlib import Path

from src.emit_html import emit_body
from src.ir import Image, Quote

HOME_URL = "https://smart-lab.ru/"
LOGIN_URL = "https://smart-lab.ru/login/"
ADD_URL = "https://smart-lab.ru/topic/add/"

# The post form (#editor_form) only renders for a logged-in user, so its title
# input doubles as the liveness marker (is_alive navigates to ADD_URL, waits).
ALIVE_SEL = "#topic_title"
TITLE_SEL = "#topic_title"
# The TinyMCE editor iframe; its presence means the editor has initialized. The
# underlying <textarea id=topic_text> is display:none, so we wait on the iframe.
BODY_SEL = "#topic_text_ifr"
EDITOR_ID = "topic_text"  # TinyMCE editor id (== textarea id) for the JS API


def build_document(page, doc, images_dir, log=print):
    images_dir = Path(images_dir)

    log(f"Opening editor ({ADD_URL})")
    page.goto(ADD_URL, wait_until="domcontentloaded")
    page.wait_for_selector(BODY_SEL, timeout=30000)

    # TinyMCE creates the iframe early but the editor object/initialized flag come a
    # beat later; using the API before that throws, so wait on .initialized.
    page.wait_for_function(
        "() => window.tinymce && window.tinymce.get('%s') && window.tinymce.get('%s').initialized" % (EDITOR_ID, EDITOR_ID),
        timeout=30000,
    )

    log(f"Title: {doc.title!r}")
    page.fill(TITLE_SEL, doc.title)

    # TinyMCE renders our emitted HTML natively (bold/italic, lists, headings, and
    # native <blockquote> — no post-pass). Images stay as [[IMG:…]] markers in 3a.
    body_html = emit_body(doc, caption_marker=False)
    log("Setting body via TinyMCE setContent…")
    page.evaluate(
        """(html) => {
            const ed = window.tinymce.get('%s');
            ed.setContent(html);
            ed.save();  // sync iframe -> textarea so submit/preview sees it
        }""" % EDITOR_ID,
        body_html,
    )

    log("Advancing to preview: «предпросмотр»")
    try:
        page.click("input[name='submit_preview']", timeout=10000)
        log("Preview requested. Review and publish manually (never auto-published).")
    except Exception as e:  # noqa: BLE001
        log(f"Could not click «предпросмотр» ({str(e)[:80]}); advance manually.")

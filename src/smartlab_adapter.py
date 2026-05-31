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
    raise NotImplementedError(
        "smartlab build_document is finalized in Phase 3 after editor discovery"
    )

"""Drive smart-lab.ru's post editor to build a draft.

Editor engine is determined by discovery (see docs/platform-notes.md
"Smartlab"); until then BODY_SEL/TITLE_SEL/ALIVE_SEL are best-guess
placeholders and build_document's body strategy is finalized in Phase 3.

Auth is an ordinary login/password (standard Playwright login flow). We build
the body from the shared IR via emit_html.emit_body, drive the editor to a
draft/preview, and STOP — never publish.
"""
from pathlib import Path

from src.emit_html import emit_body
from src.ir import Image, Quote

HOME_URL = "https://smart-lab.ru/"
LOGIN_URL = "https://smart-lab.ru/login/"
ADD_URL = "https://smart-lab.ru/topic/add/"

# Confirmed at discovery (Phase 2). ALIVE_SEL must be an element that renders
# ONLY for a logged-in user (is_alive navigates to ADD_URL and waits for it).
ALIVE_SEL = "#title"      # placeholder — title field of the post form
TITLE_SEL = "#title"      # placeholder
BODY_SEL = "#text"        # placeholder — editor body / textarea


def build_document(page, doc, images_dir, log=print):
    raise NotImplementedError(
        "smartlab build_document is finalized in Phase 3 after editor discovery"
    )

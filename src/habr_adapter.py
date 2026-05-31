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
from src.emit_html import emit_body  # noqa: F401  (used once build_document is implemented)

HOME_URL = "https://habr.com/ru/feed/"
LOGIN_URL = "https://habr.com/ru/auth/login/"
# The "write" pencil in the top navbar routes to the right editor for the account
# (sandbox or full); it renders only for a logged-in user, so it doubles as the
# liveness marker.
PENCIL_SEL = "a:has(svg.tm-header-user-menu__icon_write)"
ALIVE_SEL = PENCIL_SEL

BODY_SEL = ".tiptap.ProseMirror"
TITLE_SEL = ".tiptap .title"            # first node of the doc (<h1 class="title">)
SETTINGS_BUTTON_TEXT = "Далее к настройкам"


def build_document(page, doc, images_dir):
    raise NotImplementedError(
        "Habr build_document is not implemented yet — see Task 4+ in "
        "docs/plans/2026-05-31-habr-adapter.md."
    )

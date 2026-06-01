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
from src.ir import Image, Quote

HOME_URL = "https://habr.com/ru/feed/"
LOGIN_URL = "https://habr.com/ru/auth/login/"
# Direct editor URL — the navbar pencil became a <button>-popup (no longer an <a>),
# so opening by URL is the reliable path; the pencil click is kept as a fallback.
NEW_ARTICLE_URL = "https://habr.com/ru/article/new/"
# The "write" pencil in the top navbar routes to the right editor for the account
# (sandbox or full); it renders only for a logged-in user, so it doubles as the
# liveness marker.
PENCIL_SEL = "a:has(svg.tm-header-user-menu__icon_write)"

BODY_SEL = ".tiptap.ProseMirror"
# Liveness: the editor body only mounts for a logged-in user. The old navbar-pencil
# selector broke when the pencil became a <button> popup, so we check the editor body
# at the new-article URL instead (the same selector build_document waits for).
ALIVE_SEL = BODY_SEL
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


# Each block carries a per-block menu; for a text block it offers «Цитата». Match the
# paragraph by its content text (menu/drag text stripped), then JS-click «Цитата».
_CONVERT_QUOTE_JS = r"""
(text) => {
  const pm = document.querySelector('.tiptap.ProseMirror');
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const target = norm(text);
  for (const b of pm.querySelectorAll('.node_paragraph')) {
    const clone = b.cloneNode(true);
    clone.querySelectorAll('.right-menu__container,.node__drag-control,.context-menu')
         .forEach(n => n.remove());
    if (norm(clone.textContent) !== target) continue;
    const btn = [...b.querySelectorAll('button.right-menu__item')]
                  .find(x => norm(x.textContent) === 'Цитата');
    if (btn) { btn.click(); return true; }
  }
  return false;
}
"""

# Caption field = a <figcaption class="node_figcaption"> (placeholder «Подпись к
# изображению») in the n-th image block. Return its on-screen point for a real click.
_CAPTION_POINT_JS = r"""
(n) => {
  const pm = document.querySelector('.tiptap.ProseMirror');
  const imgs = [...pm.querySelectorAll('img')];
  const img = imgs[n];
  if (!img) return null;
  let block = img;
  while (block.parentElement && block.parentElement !== pm) block = block.parentElement;
  const cap = block.querySelector('figcaption.node_figcaption')
           || block.querySelector('[data-placeholder="Подпись к изображению"]');
  if (!cap) return null;
  cap.scrollIntoView({block: 'center'});
  let r = cap.getBoundingClientRect();
  if (r.height < 4) {
    const ir = img.getBoundingClientRect();
    r = {x: ir.x, y: ir.bottom + 6, width: ir.width, height: 14};
  }
  return {x: r.x + Math.min(40, r.width / 2), y: r.y + r.height / 2};
}
"""


def _convert_quotes(page, doc, log):
    """Convert each pasted quote (which lands as a plain paragraph) to a native quote."""
    quotes = [b for b in doc.blocks if isinstance(b, Quote)]
    if not quotes:
        return
    log(f"Converting {len(quotes)} quote(s) to native blocks…")
    for q in quotes:
        text = "".join(r.text for r in q.runs)
        try:
            if not page.evaluate(_CONVERT_QUOTE_JS, text):
                log(f"  quote not matched: {text[:40]!r}")
        except Exception as e:  # noqa: BLE001 — best-effort per quote
            log(f"  quote convert failed: {str(e)[:60]}")


def _set_captions(page, doc, log):
    """Type each image's caption into its native «Подпись к изображению» field."""
    images = [b for b in doc.blocks if isinstance(b, Image)]
    todo = [(i, b) for i, b in enumerate(images) if b.caption]
    if not todo:
        return
    log(f"Setting {len(todo)} caption(s)…")
    for idx, block in todo:
        text = "".join(r.text for r in block.caption)
        try:
            point = page.evaluate(_CAPTION_POINT_JS, idx)
            if not point:
                log(f"  caption field not found for image #{idx}")
                continue
            page.mouse.click(point["x"], point["y"])
            page.keyboard.type(text)
            time.sleep(0.2)
        except Exception as e:  # noqa: BLE001 — best-effort per caption
            log(f"  caption set failed (#{idx}): {str(e)[:60]}")


def build_document(page, doc, images_dir, log=print):
    images_dir = Path(images_dir)

    log(f"Opening editor at {NEW_ARTICLE_URL}")
    page.goto(NEW_ARTICLE_URL, wait_until="domcontentloaded")
    try:
        page.wait_for_selector(BODY_SEL, timeout=15000)
    except Exception:  # noqa: BLE001 — fall back to the navbar pencil
        log("Direct editor URL didn't load body; falling back to the navbar pencil")
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

    _convert_quotes(page, doc, log)
    _set_captions(page, doc, log)

    log(f"Advancing to settings: «{SETTINGS_BUTTON_TEXT}»")
    try:
        page.locator(f"button:has-text('{SETTINGS_BUTTON_TEXT}')").first.click(timeout=10000)
        log("On the settings screen. Stopping (fill hubs/audience/keywords and publish manually).")
    except Exception as e:  # noqa: BLE001
        log(f"Could not click «{SETTINGS_BUTTON_TEXT}» ({str(e)[:80]}); advance manually.")

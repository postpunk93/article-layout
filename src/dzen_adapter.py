"""Drive Yandex Dzen's article editor (Draft.js) to build an autosaved draft.

See docs/plans/2026-05-31-dzen-adapter-design.md. Dzen attaches to a LIVE Chrome
via connect_over_cdp (the master Yandex SSO cookie is session-scoped, so the
Habr "login then reopen profile" scheme bounces to passport). One real clipboard
paste carries headings/paragraphs/bold/italic/quotes/lists natively; only images
need a native-upload pass; stop at autosave, never publish.
"""
import time
from pathlib import Path

from src.emit_html import emit_body
from src.ir import Image

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


def _open_editor(page, log):
    """From a logged-in live session, open a fresh article editor and return when the
    body contenteditable is present."""
    if "/edit" in page.url:
        try:
            page.wait_for_selector(BODY_SEL, timeout=4000)
            return
        except Exception:  # noqa: BLE001
            pass
    log("Opening Dzen studio…")
    page.goto(STUDIO_URL, wait_until="domcontentloaded")
    page.wait_for_selector(ADD_PUBLICATION_SEL, timeout=30000)  # logged-in marker
    page.locator(ADD_PUBLICATION_SEL).first.click()
    page.wait_for_timeout(800)
    for item in ["text=Написать статью", "text=Статья"]:
        loc = page.locator(item)
        if loc.count():
            loc.first.click()
            break
    page.wait_for_selector(BODY_SEL, timeout=20000)
    log(f"Article editor: {page.url}")


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
    page.click(TITLE_SEL)
    page.keyboard.type(doc.title)
    # Move into the body and paste the whole structure with one real Ctrl+V.
    html = body_html(doc)
    _set_clipboard(page, html)
    page.click(BODY_SEL)
    page.keyboard.press("Control+V")
    page.wait_for_timeout(1500)
    log("Body pasted.")


def _replace_marker_with_image(page, block, path, log):
    needle = f"[[IMG:{block.file}]]"
    # Find and focus the marker block, then clear its text so the upload lands in place.
    idx = page.evaluate(
        """(needle) => {
            const bs = [...document.querySelectorAll('[data-editor="ZenDraftEditor"][data-block="true"]')];
            return bs.findIndex(el => (el.innerText || '').includes(needle));
        }""",
        needle,
    )
    if idx < 0:
        log(f"  marker {needle} not found — skipping")
        return
    block_loc = page.locator('[data-editor="ZenDraftEditor"][data-block="true"]').nth(idx)
    block_loc.scroll_into_view_if_needed()
    block_loc.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    # Reveal the side "+" by hovering the block's left gutter, then click it.
    # +10px puts the cursor just inside the left gutter where the "+" anchors.
    box = block_loc.bounding_box()
    if not box:
        log(f"  could not locate block gutter for {block.file} — skipping")
        return
    page.mouse.move(box["x"] + 10, box["y"] + box["height"] / 2)
    page.wait_for_selector(SIDE_BUTTON_SEL, timeout=4000)
    n_before = page.evaluate("() => document.querySelectorAll('figure.zen-editor-block-image img').length")
    page.locator(SIDE_BUTTON_SEL).first.click()
    # The side button opens an image popup carrying a hidden file input.
    page.wait_for_selector(IMAGE_FILE_INPUT_SEL, timeout=8000)
    page.locator(IMAGE_FILE_INPUT_SEL).first.set_input_files(str(path))
    # Wait for the uploaded image to get a real CDN src (avatars.dzeninfra.ru).
    page.wait_for_function(
        """(n) => {
            const imgs = document.querySelectorAll('figure.zen-editor-block-image img');
            if (imgs.length <= n) return false;
            const last = imgs[imgs.length - 1];
            return last.complete && last.naturalWidth > 0 && /^https?:/.test(last.currentSrc || last.src || '');
        }""",
        arg=n_before,
        timeout=60000,
    )
    log(f"  image: {block.file} caption={'yes' if block.caption else 'no'}")
    if block.caption:
        cap_loc = page.locator(FIGCAPTION_SEL).last
        cap_loc.click()
        page.keyboard.type("".join(r.text for r in block.caption))
    time.sleep(0.3)


def build_document(page, doc, images_dir, log=print):
    images_dir = Path(images_dir)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])

    _open_editor(page, log)
    _set_title_and_body(page, doc, log)

    images = [b for b in doc.blocks if isinstance(b, Image)]
    log(f"Uploading {len(images)} image(s)…")
    for block in images:
        path = images_dir / block.file
        if not path.exists():
            log(f"  IMAGE MISSING ON DISK: {path} — leaving marker [[IMG:{block.file}]]")
            continue
        try:
            _replace_marker_with_image(page, block, path, log)
        except Exception as e:  # noqa: BLE001 — report and continue
            log(f"  image {block.file} failed ({str(e)[:80]}) — marker left in body")

    # Stop at the autosaved draft — NEVER click «Опубликовать». The paste and image
    # uploads already dirty the editor, so autosave fires on its own; we just wait for
    # the status to read the verified "Все изменения сохранены" (match the full phrase
    # so a transient "Сохранение…" / "saving" state doesn't satisfy it early).
    try:
        page.wait_for_function(
            """(sel) => {
                const s = document.querySelector(sel);
                return s && /все изменения сохранен/i.test(s.innerText || '');
            }""",
            arg=STATUS_SEL,
            timeout=20000,
        )
        log("Draft autosaved.")
    except Exception:  # noqa: BLE001
        log(f"WARNING: did not observe autosave status; draft may still be saving. URL: {page.url}")

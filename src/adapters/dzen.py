"""Drive Yandex Dzen's article editor (Draft.js) to build an autosaved draft.

See docs/plans/2026-05-31-dzen-adapter-design.md. Like Habr, login needs a non-CDP
Chrome (Yandex SmartCaptcha), so the dzen platform entry sets manual_login; once the
profile is logged in, layout/status reuse it through the standard open_context
(Yandex marks the device trusted and the session survives). One real clipboard paste
carries headings/paragraphs/bold/italic/quotes/lists natively; only images need a
native-upload pass; stop at autosave, never publish.
"""
import time
from pathlib import Path

from src.emit_html import emit_body
from src.ir import Image

# Studio dashboard; /profile/editor/create redirects here when logged in.
STUDIO_URL = "https://dzen.ru/profile/editor/create"

ADD_PUBLICATION_SEL = '[data-testid="add-publication-button"]'   # the "+" in the studio header
BODY_SEL = '.public-DraftEditor-content[spellcheck="true"]'      # body contenteditable (title is spellcheck=false)
TITLE_SEL = '.public-DraftEditor-content[spellcheck="false"]'    # title contenteditable
STATUS_SEL = '[class*="editor-header__status"]'                  # autosave indicator
SIDE_BUTTON_SEL = '[class*="side-button__sideButton"]'           # reveal-on-hover image "+"
UPLOAD_BTN_TEXT = "Загрузите файл"                               # in the image popup; fires a file chooser
CAPTION_SEL = 'textarea[class*="image-caption__input"]'         # uploaded image's caption field
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
    # Primary is the exact menu label; the fallback is an EXACT "Статья" match
    # (quoted) so it can't catch other publication types containing the word.
    for item in ["text=Написать статью", 'text="Статья"']:
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
    # Bring the tab to the foreground: a real Ctrl+V only pastes the system clipboard
    # into a FOCUSED tab (a background tab pastes empty).
    page.bring_to_front()
    page.click(TITLE_SEL)
    page.keyboard.type(doc.title)
    # Move into the body and paste the whole structure with one real Ctrl+V.
    html = body_html(doc)
    _set_clipboard(page, html)
    page.click(BODY_SEL)
    page.keyboard.press("ControlOrMeta+V")
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
    # Empty ONLY this marker block. DraftJS treats Ctrl+A as "select the whole editor",
    # so Ctrl+A + Delete would wipe the entire body — select just this line instead.
    page.keyboard.press("Home")
    page.keyboard.press("Shift+End")
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
    # The side button opens an image popup whose "Загрузите файл" button fires a native
    # file chooser. The popup's own <input type=file> is display:none, so a
    # visibility-waiting set_input_files would hang — intercept the chooser instead.
    with page.expect_file_chooser(timeout=10000) as fc:
        page.get_by_text(UPLOAD_BTN_TEXT).first.click()
    fc.value.set_files(str(path))
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
        cap_loc = page.locator(CAPTION_SEL).last
        cap_loc.click()
        page.keyboard.type("".join(r.text for r in block.caption))
    time.sleep(0.3)


def _strip_blank_after_images(page, log):
    """Remove the blank paragraph each image insert leaves after its figure (the
    emptied marker block). For each figure→blank→PARAGRAPH triple, click the blank and
    forward-Delete to merge the next paragraph UP into it.

    Two hard constraints, both load-bearing:
    - forward-Delete (merge DOWN) keeps the atomic image above untouched; a Backspace
      (merge UP) would merge INTO the image and DELETE it.
    - we only merge when the block after the blank is a `zen-editor-block-paragraph`.
      The merged block keeps the blank's PARAGRAPH type, so merging a heading/list/quote
      there would DEMOTE it (e.g. a subheading becomes bold body text). When the next
      block isn't a plain paragraph we leave the blank — a section break before a
      heading is harmless, a demoted heading is not."""
    sel = "[data-editor=ZenDraftEditor][data-block=true]"
    removed = 0
    for _ in range(40):  # one pass removes one blank; guard against a stuck scan
        idx = page.evaluate(
            """(sel) => {
                const bs = [...document.querySelectorAll(sel)];
                for (let i = 0; i < bs.length - 2; i++) {
                    if (/zen-editor-block-image/.test(bs[i].className) &&
                        (bs[i + 1].innerText || '').trim() === '' &&
                        !/zen-editor-block-image/.test(bs[i + 1].className) &&
                        /zen-editor-block-paragraph/.test(bs[i + 2].className)) return i + 1;
                }
                return -1;
            }""",
            sel,
        )
        if idx < 0:
            break
        blk = page.locator(sel).nth(idx)
        blk.scroll_into_view_if_needed()
        blk.click()
        page.keyboard.press("End")
        page.keyboard.press("Delete")
        page.wait_for_timeout(150)
        removed += 1
    if removed:
        log(f"Removed {removed} blank line(s) after images.")


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

    _strip_blank_after_images(page, log)

    # Stop at the autosaved draft — NEVER click «Опубликовать». The paste and image
    # uploads already dirty the editor, so autosave fires on its own; wait for the status
    # to read a SAVED state ("Сохранено …" / "Все изменения сохранены") — the `[оы]` ending
    # matches сохранен-о/сохранен-ы but NOT the in-progress "Сохранение…".
    try:
        page.wait_for_function(
            """(sel) => {
                const s = document.querySelector(sel);
                return s && /сохранен[оы]/i.test(s.innerText || '');
            }""",
            arg=STATUS_SEL,
            timeout=20000,
        )
        log("Draft autosaved.")
    except Exception:  # noqa: BLE001
        log(f"WARNING: did not observe autosave status; draft may still be saving. URL: {page.url}")

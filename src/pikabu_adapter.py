"""Drive the Pikabu (Tiptap / ProseMirror) editor to build a draft from a Document.

Unlike VC (Editor.js, lossy paste → block-by-block typing), Pikabu's Tiptap editor
accepts HIGH-FIDELITY HTML paste, so the whole body goes in ONE paste — headings,
paragraphs, bold/italic, bullet/ordered lists and blockquotes all survive (see
experiments/04-pikabu-editor/notes.md).

Images can't be pasted as <img> (the editor only keeps images it uploaded itself),
so the body carries [[IMG:file]] marker paragraphs. Afterwards each marker is
replaced IN PLACE by pasting the real image File: Tiptap intercepts the File on a
synthetic `paste` event and uploads it to Pikabu's CDN (cs*.pikabu.ru). The image
node has a NATIVE caption field, written straight from the IR.

Visible browser, persistent profile, STOPS at a saved draft (never publishes).
"""
import base64
import mimetypes
import time
from pathlib import Path

from src.emit_html import emit_body
from src.ir import Image

ADD_URL = "https://pikabu.ru/add"
TITLE_SEL = 'textarea[placeholder="Заголовок"]'
BODY_SEL = ".tiptap.ProseMirror"
# The just-uploaded image's native caption is a ProseMirror node-content div inside
# the image node's caption host. Scope to the caption host so it doesn't match the
# data-node-view-content of ordinary paragraphs.
CAPTION_SEL = f"{BODY_SEL} .node-image-caption-view__host [data-node-view-content]"
SAVE_DRAFT_TEXT = "Сохранить черновик"
# Clicking «Сохранить черновик» fires this POST; a 200 means the draft persisted.
# The editor URL never changes (/add is always a fresh post) — the saved draft
# appears in the drafts list instead.
SAVE_DRAFT_MARKER = "save_draft_post"
DRAFTS_URL = "https://pikabu.ru/drafts"


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


def _select_img_marker(page, filename):
    """Select the [[IMG:filename]] marker paragraph's contents. Returns True if found."""
    return page.evaluate(
        """(fname) => {
            const el = document.querySelector('.tiptap.ProseMirror');
            const needle = '[[IMG:' + fname + ']]';
            const p = [...el.querySelectorAll('p')].find(
                n => (n.textContent || '').includes(needle));
            if (!p) return false;
            const range = document.createRange();
            range.selectNodeContents(p);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            el.focus();
            return true;
        }""",
        filename,
    )


def _paste_image_file(page, image_path):
    """Paste a real image File over the current selection; wait for the CDN upload.

    Tiptap replaces the selected marker text with an image node, shows a blob:
    placeholder, then swaps in the uploaded https src once the upload completes.
    """
    image_path = Path(image_path)
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    mime = mimetypes.guess_type(image_path.name)[0] or "image/png"
    n_before = page.evaluate(f"() => document.querySelectorAll('{BODY_SEL} img').length")
    page.evaluate(
        """async ({b64, name, mime}) => {
            const res = await fetch('data:' + mime + ';base64,' + b64);
            const blob = await res.blob();
            const file = new File([blob], name, {type: mime});
            const dt = new DataTransfer();
            dt.items.add(file);
            const el = document.querySelector('.tiptap.ProseMirror');
            el.focus();
            el.dispatchEvent(new ClipboardEvent('paste',
                {clipboardData: dt, bubbles: true, cancelable: true}));
        }""",
        {"b64": b64, "name": image_path.name, "mime": mime},
    )
    # CRITICAL: upload is async. Wait until a NEW <img> exists and has swapped its
    # blob: placeholder for a real https src — otherwise later steps run too early.
    page.wait_for_function(
        """(n) => {
            const imgs = document.querySelectorAll('.tiptap.ProseMirror img');
            if (imgs.length <= n) return false;
            const last = imgs[imgs.length - 1];
            return last.complete && last.naturalWidth > 0 &&
                   /^https?:/.test(last.currentSrc || last.src || '');
        }""",
        arg=n_before,
        timeout=90000,
    )


def _set_last_image_caption(page, text):
    """Type the caption into the just-uploaded (last) image's native caption field.

    A programmatic DOM range does NOT reliably sync to ProseMirror's selection, and
    a locator click stalls on the (often ~0-height) caption host. Instead compute the
    caption host's on-screen point and fire a REAL page.mouse.click there — that makes
    the browser set the DOM selection, which PM then adopts — and type. Falls back to
    a point just below the image if the host has collapsed height.
    """
    point = page.evaluate(
        """() => {
            const imgs = document.querySelectorAll('.tiptap.ProseMirror img');
            const img = imgs[imgs.length - 1];
            if (!img) return null;
            const figureHost = img.closest('.node-image-view__host');
            const host = figureHost && figureHost.querySelector('.node-image-caption-view__host');
            // CRITICAL: the click is by viewport coordinates, so the target must be
            // ON screen. In a long article the image is scrolled out of view and a
            // raw getBoundingClientRect() y would miss — scroll it into view first.
            (host || img).scrollIntoView({block: 'center'});
            let r = host && host.getBoundingClientRect();
            if (!r || r.height < 4) {
                const ir = img.getBoundingClientRect();
                r = {x: ir.x, y: ir.bottom + 6, width: ir.width, height: 12};
            }
            return {x: r.x + Math.min(40, r.width / 2), y: r.y + r.height / 2};
        }"""
    )
    if not point:
        return
    page.mouse.click(point["x"], point["y"])
    page.keyboard.type(text)


def _delete_leftover_marker_paragraph(page):
    """Remove the empty paragraph left where the [[IMG:]] marker text used to be.

    Replacing the marker's inline text with an image (a block node) leaves the now
    empty paragraph just BEFORE the image. Put the caret at its start and Backspace
    to merge it into the preceding block (no-op text-wise), dropping the blank line.
    """
    placed = page.evaluate(
        """() => {
            const root = document.querySelector('.tiptap.ProseMirror');
            const imgs = root.querySelectorAll('img');
            const img = imgs[imgs.length - 1];
            if (!img) return false;
            let block = img;                       // climb to the image's top-level block
            while (block.parentElement && block.parentElement !== root)
                block = block.parentElement;
            const prev = block.previousElementSibling;
            if (!prev || (prev.innerText || '').trim() !== '') return false;
            const range = document.createRange();
            range.selectNodeContents(prev);
            range.collapse(true);                  // caret at start of the empty block
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            root.focus();
            return true;
        }"""
    )
    if placed:
        page.keyboard.press("Backspace")


def build_document(page, doc, images_dir: Path, log=print):
    log(f"Opening editor: {ADD_URL}")
    page.goto(ADD_URL, wait_until="domcontentloaded")
    page.wait_for_selector(BODY_SEL, timeout=30000)
    time.sleep(2)

    log(f"Title: {doc.title!r}")
    page.click(TITLE_SEL)
    page.keyboard.type(doc.title)

    # Whole body in one high-fidelity paste (no caption markers — captions are set
    # later into each image's native caption field).
    log("Pasting body HTML…")
    body_html = emit_body(doc, caption_marker=False)
    page.click(BODY_SEL)
    _paste_html(page, body_html)
    time.sleep(1.0)

    # Replace each [[IMG:file]] marker, in document order, with the uploaded image.
    images = [b for b in doc.blocks if isinstance(b, Image)]
    log(f"Uploading {len(images)} image(s)…")
    for idx, block in enumerate(images):
        path = images_dir / block.file
        if not path.exists():
            log(f"  IMAGE MISSING ON DISK: {path} — skipping marker (left in body)")
            continue
        if not _select_img_marker(page, block.file):
            log(f"  marker [[IMG:{block.file}]] not found in body — skipping")
            continue
        cap = "".join(r.text for r in block.caption) if block.caption else ""
        log(f"  [{idx}] {block.file} caption={'yes' if cap else 'no'}")
        _paste_image_file(page, path)
        if cap:
            _set_last_image_caption(page, cap)
        _delete_leftover_marker_paragraph(page)
        time.sleep(0.3)

    # Save a draft (never publish). Wait for the save_draft_post response as the
    # confirmation signal. Best-effort: leave the window open regardless.
    log("Saving draft…")
    try:
        with page.expect_response(lambda r: SAVE_DRAFT_MARKER in r.url, timeout=12000) as resp:
            page.locator(f"button:has-text('{SAVE_DRAFT_TEXT}')").first.click(timeout=8000)
        log(f"Draft saved (save_draft_post {resp.value.status}). Find it at {DRAFTS_URL}")
    except Exception as e:
        log(f"Could not confirm draft save ({str(e)[:80]}); save it manually via «{SAVE_DRAFT_TEXT}».")

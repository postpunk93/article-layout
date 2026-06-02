"""Drive the WordPress / Gutenberg editor (ruminlab.ru) to build a draft.

One real Ctrl+V of our clean body HTML produces native Gutenberg blocks
(headings, lists, quote, bold/italic) and auto-sideloads <img> data-URIs into
the media library. The canvas is in an iframe, but the wp.data store lives on
the TOP window, so the title, image captions, and "save draft" are driven via
wp.data — the iframe is touched only for the single body paste. Visible browser,
shared client profile, STOPS at a saved draft (never publishes).
"""
import base64
import mimetypes
import time
from pathlib import Path

from src.emit_html import emit_body
from src.ir import Image

SITE = "https://ruminlab.ru"
EDITOR_URL = f"{SITE}/wp-admin/post-new.php"
ALIVE_SEL = ".editor-document-tools__inserter-toggle"
CANVAS_SEL = 'iframe[name="editor-canvas"]'


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def body_html(doc, images_dir: Path) -> str:
    """Clean Gutenberg-paste HTML: real <blockquote>, <img> as data-URIs (WP
    sideloads them to the media library on paste), and captions as [[CAP:text]]
    marker paragraphs that the post-paste cleanup pass moves into each image's
    native caption."""
    return emit_body(
        doc, quote_as_paragraph=False, caption_marker=True, img_sep=" ",
        image_src=lambda f: _data_uri(images_dir / f),
    )


def _set_clipboard(page, html):
    """Put clean body HTML on the real clipboard (text/html + text/plain).

    A real Ctrl+V of THIS clean html is what Gutenberg parses into one core block
    per element. Requires clipboard-write permission (granted in build_document).
    """
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


# Editor is ready when the block-editor store is up (logged in AND editor loaded).
# wp.data lives on the TOP window regardless of the iframed canvas.
_EDITOR_READY = ("() => !!(window.wp && wp.data && wp.data.select('core/block-editor')"
                 " && wp.data.select('core/block-editor').getBlocks)")

_SET_TITLE = "(t) => wp.data.dispatch('core/editor').editPost({title: t})"

# Ensure a first empty paragraph block exists and return its clientId, so we can
# focus the BODY (not the title) for the paste. Pasting into the title swallows the
# first body block (observed in recon).
_FIRST_BODY_CLIENT_ID = r"""
() => {
  const sel = wp.data.select('core/block-editor');
  const dispatch = wp.data.dispatch('core/block-editor');
  const blocks = sel.getBlocks();
  if (blocks.length) return blocks[0].clientId;
  const b = wp.blocks.createBlock('core/paragraph');
  dispatch.insertBlocks(b);
  return b.clientId;
}
"""

# All core/image blocks have a real http(s) url (WP finished sideloading them).
_IMAGES_SETTLED = r"""
() => {
  const imgs = wp.data.select('core/block-editor').getBlocks()
      .filter(b => b.name === 'core/image');
  return imgs.length === 0 || imgs.every(b => /^https?:/.test(b.attributes.url || ''));
}
"""

# Move each [[CAP:text]] paragraph that immediately follows a core/image into that
# image's native caption, then remove the marker paragraph. Returns the count set.
_APPLY_CAPTIONS = r"""
() => {
  const sel = wp.data.select('core/block-editor');
  const dispatch = wp.data.dispatch('core/block-editor');
  const blocks = sel.getBlocks();
  const text = a => (typeof a.content === 'string') ? a.content
                  : (a.content && a.content.text) ? a.content.text : '';
  const decode = s => { const t = document.createElement('textarea'); t.innerHTML = s; return t.value; };
  let n = 0;
  for (let i = 0; i < blocks.length - 1; i++) {
    if (blocks[i].name !== 'core/image') continue;
    const next = blocks[i + 1];
    if (next.name !== 'core/paragraph') continue;
    const m = text(next.attributes).match(/^\s*\[\[CAP:([\s\S]*)\]\]\s*$/);
    if (!m) continue;
    dispatch.updateBlockAttributes(blocks[i].clientId, {caption: decode(m[1])});
    dispatch.removeBlock(next.clientId);
    n++;
  }
  return n;
}
"""

_SAVE_DRAFT = "() => wp.data.dispatch('core/editor').savePost()"

# Saved as a draft: not currently saving AND status is 'draft'.
_DRAFT_SAVED = r"""
() => {
  const s = wp.data.select('core/editor');
  return !s.isSavingPost() && s.getCurrentPost().status === 'draft';
}
"""


def build_document(page, doc, images_dir: Path, log=print):
    log(f"Opening editor: {EDITOR_URL}")
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.goto(EDITOR_URL, wait_until="domcontentloaded")
    page.wait_for_function(_EDITOR_READY, timeout=30000)
    time.sleep(1)

    # 1. Title via wp.data (pasting into the title field would swallow the first block).
    log(f"Title: {doc.title!r}")
    page.evaluate(_SET_TITLE, doc.title)

    # 2. Body in ONE real Ctrl+V into the first body block (inside the canvas iframe).
    html = body_html(doc, images_dir)
    _set_clipboard(page, html)
    client_id = page.evaluate(_FIRST_BODY_CLIENT_ID)
    # insertBlocks updates the store synchronously but the iframe React-renders the
    # block async; the Playwright locator auto-waits for it before clicking. A failed
    # focus here means a bad paste, so it is intentionally NOT wrapped in try/except.
    # A paragraph block's editable IS the [data-block] element itself (not a child),
    # so match the element OR a nested editable (other block types nest it).
    page.frame_locator(CANVAS_SEL).locator(
        f'[data-block="{client_id}"][contenteditable="true"], '
        f'[data-block="{client_id}"] [contenteditable="true"]').first.click()
    log("Pasting body via real clipboard…")
    page.keyboard.press("ControlOrMeta+V")
    # Gutenberg parses the paste asynchronously; wait for the blocks to materialize
    # instead of a fixed sleep (mirrors vc_adapter). [[CAP:]] markers add paragraphs,
    # so the top-level count is always >= the IR block count.
    try:
        page.wait_for_function(
            "(n) => wp.data.select('core/block-editor').getBlocks().length >= n",
            arg=len(doc.blocks), timeout=15000)
    except Exception:  # noqa: BLE001 — fall through; later steps are best-effort
        pass
    n_blocks = page.evaluate(
        "() => wp.data.select('core/block-editor').getBlocks().length")
    log(f"Pasted; {n_blocks} top-level block(s).")

    # 3. Wait for WP to sideload pasted data-URI images into the media library.
    n_images = sum(1 for b in doc.blocks if isinstance(b, Image))
    if n_images:
        log(f"Waiting for {n_images} image(s) to sideload to the media library…")
        try:
            page.wait_for_function(_IMAGES_SETTLED, timeout=120000)
        except Exception as e:  # noqa: BLE001 — best-effort, report and continue
            log(f"  image sideload wait timed out ({str(e)[:80]})")

    # 4. Move [[CAP:]] marker paragraphs into native image captions.
    try:
        n_caps = page.evaluate(_APPLY_CAPTIONS)
        log(f"Captions applied: {n_caps}")
    except Exception as e:  # noqa: BLE001
        log(f"  caption pass failed ({str(e)[:80]})")

    # 5. Save as a draft. NEVER publishes.
    log("Saving draft…")
    page.evaluate(_SAVE_DRAFT)
    try:
        page.wait_for_function(_DRAFT_SAVED, timeout=30000)
        log(f"Draft saved (status=draft): {page.url}")
    except Exception:  # noqa: BLE001
        status = page.evaluate(
            "() => { try { return wp.data.select('core/editor')"
            ".getCurrentPost().status; } catch (e) { return '?'; } }")
        log(f"WARNING: did not confirm draft saved (status={status}); current: {page.url}")

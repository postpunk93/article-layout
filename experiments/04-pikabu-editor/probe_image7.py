"""Marker-replacement + caption discovery for the Pikabu image node.

Now that paste-a-File uploads an image (probe_image6), the adapter plan is:
paste the whole body with [[IMG:file]] marker paragraphs, then for each marker
select its text and paste the image File so it REPLACES the marker in place.

This probe validates that flow on a small body and inspects the resulting image
node-view wrapper for any caption field (figcaption / contenteditable / input).

Writes experiments/04-pikabu-editor/probe_image7.json (UTF-8). Non-interactive.
"""
import base64
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
ADD_URL = "https://pikabu.ru/add"
BODY_SEL = ".tiptap.ProseMirror"
IMG = Path("example/lists-quotes/images/image1.png")
OUT = Path("experiments/04-pikabu-editor/probe_image7.json")

BODY_HTML = (
    "<h2>Heading</h2>"
    "<p>Intro paragraph before the image.</p>"
    "<p>[[IMG:image1.png]]</p>"
    "<p>[[CAP:This is the caption text]]</p>"
    "<p>Paragraph after the image.</p>"
)


def structure(page):
    return page.evaluate(
        """() => [...document.querySelector('.tiptap.ProseMirror').children].map(c => ({
            tag: c.tagName.toLowerCase(),
            cls: (c.className||'').toString().slice(0,40),
            text: (c.innerText||'').trim().slice(0,50),
            hasImg: !!c.querySelector('img'),
        }))"""
    )


def main():
    b64 = base64.b64encode(IMG.read_bytes()).decode()
    report = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(ADD_URL, wait_until="domcontentloaded")
        page.wait_for_selector(BODY_SEL, timeout=30000)
        page.wait_for_timeout(3000)

        # 1. Paste the body with markers.
        page.click(BODY_SEL)
        page.evaluate(
            """(html) => {
                const el = document.querySelector('.tiptap.ProseMirror');
                el.focus();
                const dt = new DataTransfer();
                dt.setData('text/html', html);
                dt.setData('text/plain', 'fallback');
                el.dispatchEvent(new ClipboardEvent('paste',
                    {clipboardData: dt, bubbles: true, cancelable: true}));
            }""",
            BODY_HTML,
        )
        page.wait_for_timeout(1200)
        report["structure_after_body"] = structure(page)

        # 2. Select the [[IMG:...]] marker paragraph's text via a DOM Range, then
        #    paste the image File so ProseMirror replaces the selection in place.
        selected = page.evaluate(
            """() => {
                const el = document.querySelector('.tiptap.ProseMirror');
                const p = [...el.querySelectorAll('p')].find(
                    n => n.innerText.includes('[[IMG:'));
                if (!p) return false;
                const range = document.createRange();
                range.selectNodeContents(p);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
                el.focus();
                return true;
            }"""
        )
        report["marker_selected"] = selected

        page.evaluate(
            """async (b64) => {
                const res = await fetch('data:image/png;base64,' + b64);
                const blob = await res.blob();
                const file = new File([blob], 'image1.png', {type: 'image/png'});
                const dt = new DataTransfer();
                dt.items.add(file);
                const el = document.querySelector('.tiptap.ProseMirror');
                el.dispatchEvent(new ClipboardEvent('paste',
                    {clipboardData: dt, bubbles: true, cancelable: true}));
            }""",
            b64,
        )
        # Wait for upload to finish (img gets an http src).
        try:
            page.wait_for_function(
                """() => {
                    const img = [...document.querySelectorAll('.tiptap.ProseMirror img')].pop();
                    return img && /^https?:/.test(img.currentSrc||img.src||'');
                }""",
                timeout=40000,
            )
            report["upload"] = "ok"
        except Exception as e:
            report["upload"] = f"timeout: {str(e)[:80]}"

        page.wait_for_timeout(1000)
        report["structure_after_image"] = structure(page)
        report["marker_still_present"] = page.evaluate(
            "() => document.querySelector('.tiptap.ProseMirror').innerText.includes('[[IMG:')"
        )

        # 3. Inspect the image node-view wrapper for a caption field.
        report["image_node"] = page.evaluate(
            """() => {
                const img = [...document.querySelectorAll('.tiptap.ProseMirror img')].pop();
                if (!img) return null;
                // climb to the outermost node-view wrapper of this image
                let w = img;
                while (w.parentElement &&
                       !w.parentElement.classList.contains('ProseMirror') &&
                       !(w.parentElement.getAttribute &&
                         w.parentElement.getAttribute('contenteditable') === 'true')) {
                    w = w.parentElement;
                }
                const caps = [];
                w.querySelectorAll(
                  'input, textarea, [contenteditable], figcaption, [class*=caption], [class*=description], [data-placeholder], [placeholder]'
                ).forEach(el => caps.push({
                    tag: el.tagName.toLowerCase(),
                    placeholder: el.getAttribute('placeholder') || el.getAttribute('data-placeholder'),
                    editable: el.getAttribute('contenteditable'),
                    cls: (el.className||'').toString().slice(0,60),
                }));
                return {
                    wrapperCls: (w.className||'').toString().slice(0,80),
                    wrapperHtml: w.outerHTML.slice(0, 2500),
                    caption_candidates: caps,
                };
            }"""
        )

        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Wrote", OUT)
        print("structure_after_body:", json.dumps(report["structure_after_body"], ensure_ascii=False))
        print("marker_selected:", report["marker_selected"], "upload:", report["upload"])
        print("marker_still_present:", report["marker_still_present"])
        print("structure_after_image:", json.dumps(report["structure_after_image"], ensure_ascii=False))
        print("caption_candidates:", json.dumps((report["image_node"] or {}).get("caption_candidates"), ensure_ascii=False))
        print("image wrapperHtml:", (report["image_node"] or {}).get("wrapperHtml", "")[:500])
        ctx.close()


if __name__ == "__main__":
    main()

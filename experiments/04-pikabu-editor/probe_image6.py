"""Upload an image by PASTING / DROPPING a real File into the Tiptap editor.

The floating "+" -> photo button does nothing observable on a trusted click
(no file chooser, no input[type=file], no XHR — see probe_image5.json). Tiptap
image extensions usually also register handlePaste/handleDrop plugins that accept
File objects from the clipboard/drag data and upload them. This probe builds a
real File (image bytes, base64 -> Blob -> File) in the page and dispatches first
a `paste`, then (if needed) a `drop` carrying it onto `.tiptap.ProseMirror`,
watching for the upload XHR + the resulting <img>.

Writes experiments/04-pikabu-editor/probe_image6.json (UTF-8). Non-interactive.
"""
import base64
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
ADD_URL = "https://pikabu.ru/add"
BODY_SEL = ".tiptap.ProseMirror"
IMG = Path("example/lists-quotes/images/image1.png")
OUT = Path("experiments/04-pikabu-editor/probe_image6.json")


def img_count(page):
    return page.evaluate(
        "() => document.querySelectorAll('.tiptap.ProseMirror img').length"
    )


def last_img(page):
    return page.evaluate(
        """() => {
            const img = [...document.querySelectorAll('.tiptap.ProseMirror img')].pop();
            if (!img) return null;
            const wrap = img.closest('[data-node-view-wrapper], [class*=node-]');
            return {
                src: (img.currentSrc||img.src||'').slice(0,100),
                isData: /^data:/.test(img.src||''),
                wrapperCls: wrap ? wrap.className.toString().slice(0,80) : null,
                wrapperHtml: wrap ? wrap.outerHTML.slice(0,1600) : null,
            };
        }"""
    )


def main():
    b64 = base64.b64encode(IMG.read_bytes()).decode()
    report = {"image_file": str(IMG.resolve()), "uploads": []}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_request(req):
            try:
                ct = req.headers.get("content-type", "")
                if "multipart" in ct or "upload" in req.url.lower():
                    report["uploads"].append({"method": req.method, "url": req.url[:160], "ct": ct[:60]})
            except Exception:
                pass

        page.on("request", on_request)

        page.goto(ADD_URL, wait_until="domcontentloaded")
        page.wait_for_selector(BODY_SEL, timeout=30000)
        page.wait_for_timeout(3000)
        page.click(BODY_SEL)
        page.wait_for_timeout(400)

        # --- attempt 1: synthetic paste carrying a File ---
        page.evaluate(
            """async (b64) => {
                const res = await fetch('data:image/png;base64,' + b64);
                const blob = await res.blob();
                const file = new File([blob], 'image1.png', {type: 'image/png'});
                const dt = new DataTransfer();
                dt.items.add(file);
                const el = document.querySelector('.tiptap.ProseMirror');
                el.focus();
                el.dispatchEvent(new ClipboardEvent('paste',
                    {clipboardData: dt, bubbles: true, cancelable: true}));
            }""",
            b64,
        )
        try:
            page.wait_for_function(
                "() => document.querySelectorAll('.tiptap.ProseMirror img').length > 0",
                timeout=8000,
            )
        except Exception:
            pass
        report["after_paste_img_count"] = img_count(page)
        report["after_paste_img"] = last_img(page)

        # --- attempt 2: synthetic drop carrying a File (if paste produced nothing) ---
        if report["after_paste_img_count"] == 0:
            page.evaluate(
                """async (b64) => {
                    const res = await fetch('data:image/png;base64,' + b64);
                    const blob = await res.blob();
                    const file = new File([blob], 'image1.png', {type: 'image/png'});
                    const dt = new DataTransfer();
                    dt.items.add(file);
                    const el = document.querySelector('.tiptap.ProseMirror');
                    const r = el.getBoundingClientRect();
                    const opts = {dataTransfer: dt, bubbles: true, cancelable: true,
                                  clientX: r.x + 40, clientY: r.y + 40};
                    el.dispatchEvent(new DragEvent('dragenter', opts));
                    el.dispatchEvent(new DragEvent('dragover', opts));
                    el.dispatchEvent(new DragEvent('drop', opts));
                }""",
                b64,
            )
            try:
                page.wait_for_function(
                    "() => document.querySelectorAll('.tiptap.ProseMirror img').length > 0",
                    timeout=8000,
                )
            except Exception:
                pass
            report["after_drop_img_count"] = img_count(page)
            report["after_drop_img"] = last_img(page)

        # If an <img> appeared with a data: src, wait to see if it converts to http (upload).
        if img_count(page) > 0:
            try:
                page.wait_for_function(
                    """() => {
                        const img = [...document.querySelectorAll('.tiptap.ProseMirror img')].pop();
                        return img && /^https?:/.test(img.currentSrc||img.src||'');
                    }""",
                    timeout=30000,
                )
                report["final_img"] = last_img(page)
                report["uploaded_to_http"] = True
            except Exception:
                report["final_img"] = last_img(page)
                report["uploaded_to_http"] = False

        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Wrote", OUT)
        print("after_paste_img_count:", report.get("after_paste_img_count"))
        print("after_drop_img_count:", report.get("after_drop_img_count"))
        print("uploaded_to_http:", report.get("uploaded_to_http"))
        print("final_img:", json.dumps(report.get("final_img"), ensure_ascii=False)[:300])
        print("uploads:", json.dumps(report["uploads"], ensure_ascii=False)[:500])
        ctx.close()


if __name__ == "__main__":
    main()

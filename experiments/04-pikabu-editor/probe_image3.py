"""Perform a real image upload via floating "+" -> photo, inspect the result.

Writes experiments/04-pikabu-editor/probe_image3.json (UTF-8). Non-interactive.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
ADD_URL = "https://pikabu.ru/add"
BODY_SEL = ".tiptap.ProseMirror"
FLOATING_SEL = ".floating-menu-view__button--HzqgG6Ir"
IMG = str(Path("example/lists-quotes/images/image1.png").resolve())
OUT = Path("experiments/04-pikabu-editor/probe_image3.json")

MENU_BTN_SEL = ".floating-menu-view__menuButton--MJpEPZAY"


def photo_button(page):
    """Return the ElementHandle of the single-photo insert button (by icon)."""
    for b in page.query_selector_all(MENU_BTN_SEL):
        href = b.eval_on_selector("use", "u => u.getAttribute('xlink:href') || u.getAttribute('href') || ''") if b.query_selector("use") else ""
        if "photo" in (href or ""):
            return b
    return None


def main():
    report = {"image_file": IMG}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(ADD_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.click(BODY_SEL)
        page.wait_for_timeout(300)
        page.click(FLOATING_SEL)
        page.wait_for_timeout(600)

        # Click the photo insert button (REAL trusted click) inside expect_file_chooser.
        try:
            btn = photo_button(page)
            report["photo_button_found"] = bool(btn)
            with page.expect_file_chooser(timeout=8000) as fc:
                btn.click()
            fc.value.set_files(IMG)
            report["file_chooser"] = "opened+set"
        except Exception as e:
            report["file_chooser"] = f"ERROR: {str(e)[:150]}"

        # Wait for the uploaded <img> to appear with a real http(s) src.
        try:
            page.wait_for_function(
                """() => {
                    const imgs = document.querySelectorAll('.tiptap.ProseMirror img');
                    if (!imgs.length) return false;
                    const last = imgs[imgs.length-1];
                    return last.complete && last.naturalWidth>0 &&
                           /^https?:/.test(last.currentSrc||last.src||'');
                }""",
                timeout=60000,
            )
            report["upload"] = "image appeared with http src"
        except Exception as e:
            report["upload"] = f"ERROR/timeout: {str(e)[:150]}"

        page.wait_for_timeout(1000)
        # Inspect the image block: its <img> src and any caption field near it.
        report["image_block"] = page.evaluate(
            """() => {
                const img = [...document.querySelectorAll('.tiptap.ProseMirror img')].pop();
                if (!img) return null;
                const wrapper = img.closest('[data-node-view-wrapper], [class*=node-]');
                return {
                    src: (img.currentSrc||img.src||'').slice(0,90),
                    wrapperCls: wrapper ? wrapper.className.toString().slice(0,80) : null,
                    wrapperHtml: wrapper ? wrapper.outerHTML.slice(0,1200) : null,
                };
            }"""
        )
        # Look for a caption input/contenteditable inside the image block.
        report["caption_candidates"] = page.evaluate(
            """() => {
                const img = [...document.querySelectorAll('.tiptap.ProseMirror img')].pop();
                if (!img) return [];
                const block = img.closest('[data-node-view-wrapper]') || img.parentElement;
                const out = [];
                block.querySelectorAll(
                  'input, textarea, [contenteditable], figcaption, [class*=caption], [class*=description]'
                ).forEach(el => out.push({
                    tag: el.tagName.toLowerCase(),
                    placeholder: el.getAttribute('placeholder')||el.getAttribute('data-placeholder'),
                    cls: (el.className||'').toString().slice(0,60),
                }));
                return out;
            }"""
        )

        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Wrote", OUT)
        print("file_chooser:", report["file_chooser"])
        print("upload:", report["upload"])
        print("image_block src:", (report.get("image_block") or {}).get("src"))
        print("caption_candidates:", json.dumps(report["caption_candidates"], ensure_ascii=False))
        ctx.close()


if __name__ == "__main__":
    main()

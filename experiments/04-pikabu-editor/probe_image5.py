"""Crack the Pikabu image upload: trusted mouse click + full network/submenu capture.

One thorough diagnostic run (each run needs the live authed browser):
  - logs ALL network requests, flags multipart/upload-looking POSTs;
  - registers a global filechooser handler (more robust than expect_file_chooser
    around a click that may open the dialog asynchronously);
  - clicks the photo button with a REAL mouse click at its bbox centre (trusted
    gesture -> should open the native chooser if that's the mechanism);
  - if nothing fires, dumps the floating menu HTML + any secondary submenu buttons
    and scans every frame for input[type=file].

Writes experiments/04-pikabu-editor/probe_image5.json (UTF-8). Non-interactive.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
ADD_URL = "https://pikabu.ru/add"
BODY_SEL = ".tiptap.ProseMirror"
FLOATING_SEL = ".floating-menu-view__button--HzqgG6Ir"
MENU_BTN_SEL = ".floating-menu-view__menuButton--MJpEPZAY"
IMG = str(Path("example/lists-quotes/images/image1.png").resolve())
OUT = Path("experiments/04-pikabu-editor/probe_image5.json")


def photo_button(page):
    for b in page.query_selector_all(MENU_BTN_SEL):
        u = b.query_selector("use")
        href = (u.get_attribute("xlink:href") or u.get_attribute("href") or "") if u else ""
        if "photo" in href:
            return b
    return None


def main():
    report = {"image_file": IMG, "requests": [], "filechooser_fired": False}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # --- network capture: flag anything POST / multipart / upload-ish ---
        def on_request(req):
            try:
                if req.method != "POST" and "upload" not in req.url.lower():
                    return
                ct = req.headers.get("content-type", "")
                report["requests"].append({
                    "method": req.method,
                    "url": req.url[:160],
                    "ct": ct[:60],
                    "multipart": "multipart" in ct,
                })
            except Exception:
                pass

        page.on("request", on_request)

        # --- global file chooser handler: auto-set the file whenever a dialog opens ---
        def on_filechooser(fc):
            report["filechooser_fired"] = True
            try:
                fc.set_files(IMG)
                report["filechooser_set"] = True
            except Exception as e:
                report["filechooser_set"] = f"ERROR: {str(e)[:120]}"

        page.on("filechooser", on_filechooser)

        page.goto(ADD_URL, wait_until="domcontentloaded")
        page.wait_for_selector(BODY_SEL, timeout=30000)
        page.wait_for_timeout(3000)
        report["logged_in"] = bool(page.query_selector(BODY_SEL))

        page.click(BODY_SEL)
        page.wait_for_timeout(400)
        page.click(FLOATING_SEL)
        page.wait_for_timeout(800)

        # Dump the floating menu container HTML (so we see exact button structure).
        report["floating_menu_html"] = page.evaluate(
            """() => {
                const b = document.querySelector('.floating-menu-view__menuButton--MJpEPZAY');
                const wrap = b ? b.closest('[class*=floating-menu]') : null;
                return wrap ? wrap.outerHTML.slice(0, 2000) : null;
            }"""
        )

        # Real trusted mouse click on the photo button by bbox centre.
        btn = photo_button(page)
        report["photo_button_found"] = bool(btn)
        if btn:
            box = btn.bounding_box()
            report["photo_bbox"] = box
            if box:
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.wait_for_timeout(2500)

        # After the click: scan EVERY frame for file inputs + any popover/submenu.
        report["file_inputs_all_frames"] = []
        for fr in page.frames:
            try:
                inputs = fr.evaluate(
                    """() => [...document.querySelectorAll('input[type=file]')].map(el => ({
                        accept: el.getAttribute('accept'),
                        cls: (el.className||'').toString().slice(0,60),
                        multiple: el.hasAttribute('multiple'),
                        visible: el.offsetParent !== null,
                    }))"""
                )
                if inputs:
                    report["file_inputs_all_frames"].append({"frame": fr.url[:80], "inputs": inputs})
            except Exception:
                pass

        # Any secondary submenu / popover that appeared after the photo click.
        report["submenu_buttons"] = page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll(
                  '[class*=popover] button, [class*=menu] button, [class*=dropdown] button, [role=menuitem], [class*=modal] button'
                ).forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0) out.push({
                        text: (el.innerText||'').trim().slice(0,40),
                        cls: (el.className||'').toString().slice(0,50),
                        dataTest: el.getAttribute('data-test'),
                    });
                });
                return out;
            }"""
        )

        # If the chooser fired and a file was set, wait for the uploaded <img>.
        if report.get("filechooser_set") is True:
            try:
                page.wait_for_function(
                    """() => {
                        const imgs = document.querySelectorAll('.tiptap.ProseMirror img');
                        if (!imgs.length) return false;
                        const last = imgs[imgs.length-1];
                        return last.complete && last.naturalWidth>0 &&
                               /^https?:/.test(last.currentSrc||last.src||'');
                    }""",
                    timeout=45000,
                )
                report["upload"] = "image appeared with http src"
            except Exception as e:
                report["upload"] = f"timeout: {str(e)[:100]}"
            report["image_block"] = page.evaluate(
                """() => {
                    const img = [...document.querySelectorAll('.tiptap.ProseMirror img')].pop();
                    if (!img) return null;
                    const wrap = img.closest('[data-node-view-wrapper], [class*=node-]');
                    return {
                        src: (img.currentSrc||img.src||'').slice(0,90),
                        wrapperCls: wrap ? wrap.className.toString().slice(0,80) : null,
                        wrapperHtml: wrap ? wrap.outerHTML.slice(0,1500) : null,
                    };
                }"""
            )

        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Wrote", OUT)
        print("logged_in:", report.get("logged_in"))
        print("photo_button_found:", report.get("photo_button_found"))
        print("filechooser_fired:", report.get("filechooser_fired"), "set:", report.get("filechooser_set"))
        print("file_inputs_all_frames:", json.dumps(report["file_inputs_all_frames"], ensure_ascii=False)[:400])
        print("submenu_buttons:", json.dumps(report["submenu_buttons"], ensure_ascii=False)[:600])
        print("upload:", report.get("upload"))
        print("requests:", json.dumps(report["requests"], ensure_ascii=False)[:600])
        ctx.close()


if __name__ == "__main__":
    main()

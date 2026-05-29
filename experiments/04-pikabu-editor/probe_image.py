"""Inspect Pikabu's floating "+" insert menu and how image upload triggers.

Writes experiments/04-pikabu-editor/probe_image.json (UTF-8). Non-interactive.
Uses example/lists-quotes/images/image1.png as the test upload.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
ADD_URL = "https://pikabu.ru/add"
BODY_SEL = ".tiptap.ProseMirror"
FLOATING_SEL = ".floating-menu-view__button--HzqgG6Ir"
IMG = str(Path("example/lists-quotes/images/image1.png").resolve())
OUT = Path("experiments/04-pikabu-editor/probe_image.json")


def main():
    report = {"image_file": IMG}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(ADD_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        # Focus the empty body so the floating "+" appears on the current line.
        page.click(BODY_SEL)
        page.keyboard.type("placeholder text")
        page.keyboard.press("Enter")
        page.wait_for_timeout(500)

        # Click the floating "+" and snapshot every data-test + visible menu item.
        page.click(FLOATING_SEL)
        page.wait_for_timeout(800)
        report["all_data_test_after_plus"] = page.evaluate(
            """() => [...document.querySelectorAll('[data-test]')].map(el => {
                const r = el.getBoundingClientRect();
                return {dt: el.getAttribute('data-test'),
                        text: (el.innerText||'').trim().slice(0,30),
                        vis: r.width>0 && r.height>0};
            }).filter(x => x.vis)"""
        )
        # Dump any popover/menu container that opened.
        report["menu_html"] = page.evaluate(
            """() => {
                const m = document.querySelector(
                  '[class*=popover]:not([style*="display: none"]), [class*=floating-menu] [class*=list], [role=menu]'
                );
                return m ? m.outerHTML.slice(0, 1500) : null;
            }"""
        )

        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Wrote", OUT)
        for x in report["all_data_test_after_plus"]:
            print(x)
        ctx.close()


if __name__ == "__main__":
    main()

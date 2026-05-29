"""Dump the floating "+" menu subtree + all button icons to find image insert.

Writes experiments/04-pikabu-editor/probe_image2.json (UTF-8). Non-interactive.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
ADD_URL = "https://pikabu.ru/add"
BODY_SEL = ".tiptap.ProseMirror"
FLOATING_SEL = ".floating-menu-view__button--HzqgG6Ir"
OUT = Path("experiments/04-pikabu-editor/probe_image2.json")


def buttons_with_icons(page):
    return page.evaluate(
        """() => [...document.querySelectorAll('button')].map(el => {
            const r = el.getBoundingClientRect();
            const use = el.querySelector('use');
            return {
                icon: use ? use.getAttribute('xlink:href') || use.getAttribute('href') : null,
                cls: (el.className||'').toString().slice(0,70),
                dt: el.getAttribute('data-test'),
                vis: r.width>0 && r.height>0,
            };
        }).filter(x => x.vis && x.icon)"""
    )


def main():
    report = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(ADD_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.click(BODY_SEL)
        page.wait_for_timeout(300)
        report["icons_before_plus"] = buttons_with_icons(page)

        # The floating "+" lives on an EMPTY line. Make sure the line is empty.
        page.click(FLOATING_SEL)
        page.wait_for_timeout(800)
        report["icons_after_plus"] = buttons_with_icons(page)

        # Full HTML of the floating-menu container (and any popover that opened).
        report["floating_container_html"] = page.evaluate(
            """() => {
                const sels = ['[class*=floating-menu]', '[class*=editor-add]',
                              '[class*=insert]', '[class*=popover]'];
                for (const s of sels) {
                    const el = document.querySelector(s);
                    if (el && el.getBoundingClientRect().width > 0)
                        return {sel: s, html: el.outerHTML.slice(0, 2500)};
                }
                return null;
            }"""
        )

        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Wrote", OUT)
        before = {b["icon"] for b in report["icons_before_plus"]}
        print("NEW icons after '+':")
        for b in report["icons_after_plus"]:
            if b["icon"] not in before:
                print(" ", b)
        ctx.close()


if __name__ == "__main__":
    main()

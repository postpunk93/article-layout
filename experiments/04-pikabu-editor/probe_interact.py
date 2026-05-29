"""Identify Pikabu (Tiptap) toolbar buttons and test keyboard formatting.

Writes a UTF-8 report to experiments/04-pikabu-editor/probe_report.json so
Russian labels/tooltips are readable. Non-interactive.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
ADD_URL = "https://pikabu.ru/add"
BODY_SEL = ".tiptap.ProseMirror"
OUT = Path("experiments/04-pikabu-editor/probe_report.json")


def main():
    report = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(ADD_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        # 1. Toolbar buttons: dump innerHTML (SVG icon) + all attributes + tooltip.
        report["toolbar_buttons"] = page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('.editor-menu__button--dVmfe_cZ').forEach((el, i) => {
                    const attrs = {};
                    for (const a of el.attributes) attrs[a.name] = a.value;
                    out.push({
                        i,
                        attrs,
                        title: el.getAttribute('title'),
                        ariaLabel: el.getAttribute('aria-label'),
                        html: el.innerHTML.slice(0, 300),
                    });
                });
                return out;
            }"""
        )

        # 2. Floating menu button (the "+" insert control).
        report["floating_menu"] = page.evaluate(
            """() => [...document.querySelectorAll('.floating-menu-view__button--HzqgG6Ir')].map(el => {
                const attrs = {}; for (const a of el.attributes) attrs[a.name] = a.value;
                return {attrs, html: el.innerHTML.slice(0, 300)};
            })"""
        )

        # 3. Type into the body and test keyboard formatting; read resulting HTML.
        page.click(BODY_SEL)
        page.keyboard.type("normal ")
        page.keyboard.press("Control+b")
        page.keyboard.type("bold")
        page.keyboard.press("Control+b")
        page.keyboard.type(" ")
        page.keyboard.press("Control+i")
        page.keyboard.type("italic")
        page.keyboard.press("Control+i")
        page.wait_for_timeout(500)
        report["body_html_after_typing"] = page.evaluate(
            f"() => document.querySelector('{BODY_SEL}').innerHTML"
        )

        # 4. Hover each toolbar button to capture any tooltip text that appears.
        tips = []
        btns = page.query_selector_all(".editor-menu__button--dVmfe_cZ")
        for i, b in enumerate(btns):
            try:
                b.hover()
                page.wait_for_timeout(350)
                tip = page.evaluate(
                    """() => {
                        const t = document.querySelector(
                          '.pkb-tooltip, [role=tooltip], .tooltip, [class*=tooltip]'
                        );
                        return t ? t.innerText.trim() : null;
                    }"""
                )
                tips.append({"i": i, "tooltip": tip})
            except Exception as e:
                tips.append({"i": i, "error": str(e)[:80]})
        report["toolbar_tooltips"] = tips

        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Wrote", OUT)
        print("toolbar buttons:", len(report["toolbar_buttons"]))
        print("body html after typing:", report["body_html_after_typing"][:200])
        ctx.close()


if __name__ == "__main__":
    main()

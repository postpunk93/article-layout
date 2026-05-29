"""Test Tiptap HTML-paste fidelity and inspect the floating "+" insert menu.

Writes experiments/04-pikabu-editor/probe_paste.json (UTF-8). Non-interactive.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
ADD_URL = "https://pikabu.ru/add"
BODY_SEL = ".tiptap.ProseMirror"
OUT = Path("experiments/04-pikabu-editor/probe_paste.json")

SAMPLE_HTML = (
    "<h2>Section heading</h2>"
    "<p>Plain <strong>bold</strong> and <em>italic</em> text.</p>"
    "<ul><li>first</li><li>second</li></ul>"
    "<ol><li>one</li><li>two</li></ol>"
    "<blockquote>A quoted line.</blockquote>"
    "<p>After quote.</p>"
)


def main():
    report = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(ADD_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        # --- 1. Paste HTML via a synthetic paste event with DataTransfer ---
        page.click(BODY_SEL)
        page.evaluate(
            """(html) => {
                const el = document.querySelector('.tiptap.ProseMirror');
                el.focus();
                const dt = new DataTransfer();
                dt.setData('text/html', html);
                dt.setData('text/plain', 'fallback');
                const ev = new ClipboardEvent('paste', {
                    clipboardData: dt, bubbles: true, cancelable: true,
                });
                el.dispatchEvent(ev);
            }""",
            SAMPLE_HTML,
        )
        page.wait_for_timeout(1000)
        # Simplified structural view: tag names + text of each top-level node.
        report["paste_structure"] = page.evaluate(
            """() => {
                function simplify(node) {
                    return [...node.children].map(c => ({
                        tag: c.tagName.toLowerCase(),
                        cls: (c.className || '').toString().slice(0, 40),
                        text: (c.innerText || '').trim().slice(0, 60),
                        kids: c.children.length,
                    }));
                }
                return simplify(document.querySelector('.tiptap.ProseMirror'));
            }"""
        )
        report["paste_html"] = page.evaluate(
            f"() => document.querySelector('{BODY_SEL}').innerHTML"
        )
        # Did headings/lists/quotes actually appear as such?
        report["paste_node_counts"] = page.evaluate(
            f"""() => {{
                const root = document.querySelector('{BODY_SEL}');
                const count = sel => root.querySelectorAll(sel).length;
                return {{
                    h1: count('h1'), h2: count('h2'), h3: count('h3'),
                    p: count('p'), ul: count('ul'), ol: count('ol'),
                    li: count('li'), blockquote: count('blockquote'),
                    b: count('b,strong'), i: count('i,em'),
                }};
            }}"""
        )

        # --- 2. Floating "+" insert menu: click it on an empty line, dump items ---
        # Add an empty paragraph at the end and focus it so the floating menu shows.
        page.keyboard.press("Control+End")
        page.keyboard.press("Enter")
        page.wait_for_timeout(500)
        floating = page.query_selector(".floating-menu-view__button--HzqgG6Ir")
        report["floating_present"] = bool(floating)
        if floating:
            try:
                floating.click()
                page.wait_for_timeout(800)
                report["insert_menu_items"] = page.evaluate(
                    """() => {
                        const out = [];
                        document.querySelectorAll(
                          '[data-test], [class*=menu] button, [class*=popover] button, [role=menuitem]'
                        ).forEach(el => {
                            const dt = el.getAttribute('data-test');
                            const t = (el.innerText || '').trim().slice(0, 30);
                            if ((dt && dt.includes('insert')) || (dt && dt.includes('add')) ||
                                (t && el.closest('[class*=menu],[class*=popover]'))) {
                                out.push({dataTest: dt, text: t,
                                          cls: (el.className||'').toString().slice(0,50)});
                            }
                        });
                        return out;
                    }"""
                )
            except Exception as e:
                report["insert_menu_error"] = str(e)[:120]

        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Wrote", OUT)
        print("node counts:", json.dumps(report.get("paste_node_counts"), ensure_ascii=False))
        print("structure:", json.dumps(report.get("paste_structure"), ensure_ascii=False)[:400])
        ctx.close()


if __name__ == "__main__":
    main()

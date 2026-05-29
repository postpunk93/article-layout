"""Discovery probe v3 (Task 6): capture the LIST block-settings popover to find
the ordered/unordered toggle. Minimal — opens the toolbox only once on the fresh
seeded block (the known-good path), inserts a list, then JS-clicks the list
block's settings gear and dumps the tunes popover.
"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE_DIR = ".vc-profile"
EDITOR_URL = "https://vc.ru/?modal=editor"
TITLE_SEL = 'div.editor-tool-input[data-placeholder="Заголовок"]'
TOOLBOX_OPEN_SEL = ".ce-popover.ce-toolbox.opened"
CAP = Path("experiments/03-vc-editor/capture")


def dump(page, label):
    CAP.mkdir(parents=True, exist_ok=True)
    try:
        html = page.eval_on_selector(".codex-editor", "el => el.outerHTML")
    except Exception as e:
        html = f"<err {e}>"
    (CAP / f"v3_{label}.html").write_text(html, encoding="utf-8")
    try:
        page.screenshot(path=str(CAP / f"v3_{label}.png"))
    except Exception:
        pass
    print(f"[dump] {label}: {len(html)} bytes", flush=True)


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(EDITOR_URL)
        try:
            page.wait_for_selector(TITLE_SEL, timeout=30000)
        except Exception:
            print("!! not logged in", flush=True); time.sleep(300); ctx.close(); return
        time.sleep(2)
        page.click(TITLE_SEL)
        page.keyboard.type("PROBE v3 list settings")
        page.keyboard.press("Enter")
        time.sleep(0.6)

        # insert a list on the fresh empty block (toolbox works here)
        page.click(".ce-toolbar__plus", timeout=8000)
        page.wait_for_selector(TOOLBOX_OPEN_SEL, timeout=8000)
        page.eval_on_selector('.ce-toolbox__item[data-type="list"]', "el => el.click()")
        time.sleep(0.8)
        page.keyboard.type("alpha")
        page.keyboard.press("Enter")
        page.keyboard.type("beta")
        time.sleep(0.4)
        dump(page, "10_list")
        print("list tag now:",
              page.eval_on_selector(".editor-list-tool", "el => el.tagName"), flush=True)

        # open the list block's settings gear (JS click bypasses hover-visibility)
        clicked = page.evaluate("""() => {
            const tool = document.querySelector('.editor-list-tool');
            if (!tool) return 'no list tool';
            const block = tool.closest('.ce-block');
            const gear = block && block.querySelector('.ce-block-action__settings-toggler');
            if (!gear) return 'no gear';
            gear.click();
            return 'clicked';
        }""")
        print("gear click:", clicked, flush=True)
        time.sleep(0.8)
        dump(page, "11_settings_open")

        # dump every visible popover + enumerate its items
        pops = page.eval_on_selector_all(
            ".ce-popover",
            "els => els.filter(e => e.offsetParent !== null).map(e => e.outerHTML)",
        )
        (CAP / "v3_settings_popovers.html").write_text(
            "\n\n=====\n\n".join(pops) or "<none visible>", encoding="utf-8")
        print(f"visible popovers: {len(pops)}", flush=True)
        items = page.eval_on_selector_all(
            ".ce-popover--opened .ce-popover-item, .ce-popover.opened .ce-popover-item, "
            ".ce-popover-item, .ce-popover__item",
            "els => els.map(e => ({text:(e.innerText||'').trim(), "
            "name:e.dataset.itemName||null, data:Object.assign({},e.dataset), "
            "aria:e.getAttribute('aria-label'), cls:e.className}))",
        )
        print("POPOVER ITEMS:", items, flush=True)
        (CAP / "v3_settings_items.txt").write_text(repr(items), encoding="utf-8")

        # Try clicking an item whose label/icon suggests ordered/numbered, then
        # re-check the tag (ul -> ol means ordered toggle found).
        switched = page.evaluate(r"""() => {
            const items = Array.from(document.querySelectorAll('.ce-popover-item, .ce-popover__item'));
            const cand = items.find(e => /нумер|order|number|1\./i.test((e.innerText||'') + ' ' + (e.getAttribute('aria-label')||'') + ' ' + JSON.stringify(e.dataset)));
            if (!cand) return {found:false, items: items.map(e=>(e.innerText||'').trim())};
            cand.click();
            return {found:true, clicked:(cand.innerText||'').trim()};
        }""")
        print("ordered-toggle attempt:", switched, flush=True)
        time.sleep(0.8)
        try:
            tag2 = page.eval_on_selector(".editor-list-tool", "el => el.tagName")
        except Exception:
            tag2 = "?"
        print("list tag AFTER toggle attempt:", tag2, flush=True)
        dump(page, "12_after_toggle")

        print("PROBE v3 DONE. Browser open ~4 min. URL:", page.url, flush=True)
        time.sleep(240)
        ctx.close()


if __name__ == "__main__":
    main()

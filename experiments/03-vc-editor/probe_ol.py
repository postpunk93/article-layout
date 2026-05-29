"""Probe v5 (Task 6): reveal the ORDERED list element after toggling 'Нумерованный'.
Robust: never let one failed query abort the run; dump HTML of the list block
before and after the toggle so we can read the real tag/class for <ol>.
"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".vc-profile"
EDITOR_URL = "https://vc.ru/?modal=editor"
TITLE_SEL = 'div.editor-tool-input[data-placeholder="Заголовок"]'
TOOLBOX_OPEN_SEL = ".ce-popover.ce-toolbox.opened"
CAP = Path("experiments/03-vc-editor/capture")


def list_block_html(page):
    return page.evaluate("""() => {
        const b = document.querySelector('.codex-editor .ce-block');
        // find the block whose content holds a UL/OL
        for (const blk of document.querySelectorAll('.ce-block')) {
            const el = blk.querySelector('ul, ol');
            if (el) return {tag: el.tagName, cls: el.className, html: blk.querySelector('.ce-block__content').innerHTML.slice(0,400)};
        }
        return {tag:null, cls:null, html:'<no ul/ol>'};
    }""")


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(EDITOR_URL)
        try:
            page.wait_for_selector(TITLE_SEL, timeout=30000)
        except Exception:
            print("!! not logged in", flush=True); time.sleep(200); ctx.close(); return
        time.sleep(2)
        page.click(TITLE_SEL); page.keyboard.type("PROBE v5 ol"); page.keyboard.press("Enter")
        time.sleep(0.6)
        try:
            page.click(".ce-toolbar__plus", timeout=4000)
        except Exception:
            page.eval_on_selector(".ce-toolbar__plus", "el=>el.click()")
        page.wait_for_selector(TOOLBOX_OPEN_SEL, timeout=8000)
        page.eval_on_selector('.ce-toolbox__item[data-type="list"]', "el=>el.click()")
        time.sleep(0.7)
        page.keyboard.type("alpha"); page.keyboard.press("Enter"); page.keyboard.type("beta")
        time.sleep(0.3)
        before = list_block_html(page)
        print("BEFORE toggle:", before["tag"], "| cls=", ascii(before["cls"] or ""), flush=True)
        (CAP / "v5_before.html").write_text(before["html"], encoding="utf-8")

        # open gear + click Нумерованный
        page.evaluate("""() => {
            const ul=document.querySelector('ul, ol');
            const g=ul.closest('.ce-block').querySelector('.ce-block-action__settings-toggler');
            g.click();
        }""")
        time.sleep(0.7)
        clicked = page.evaluate(r"""() => {
            const it=[...document.querySelectorAll('.ce-block-settings__item')].find(e=>/Нумерованный/i.test(e.innerText||''));
            if(it){it.click(); return true;} return false;
        }""")
        print("clicked Нумерованный:", clicked, flush=True)
        time.sleep(0.8)
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        time.sleep(0.4)
        after = list_block_html(page)
        print("AFTER toggle:", after["tag"], "| cls=", ascii(after["cls"] or ""), flush=True)
        (CAP / "v5_after.html").write_text(after["html"], encoding="utf-8")
        try:
            page.screenshot(path=str(CAP / "v5_after.png"))
        except Exception:
            pass
        print("PROBE v5 DONE. Browser open ~3 min.", flush=True)
        time.sleep(180)
        ctx.close()


if __name__ == "__main__":
    main()

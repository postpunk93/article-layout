"""Probe v6 (Task 6): decisive capture of the ordered-list state. Toggle
'Нумерованный', wait, NO Escape, then dump full editor HTML + screenshot and
report the content-tool element of every block.
"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".vc-profile"
EDITOR_URL = "https://vc.ru/?modal=editor"
TITLE_SEL = 'div.editor-tool-input[data-placeholder="Заголовок"]'
TOOLBOX_OPEN_SEL = ".ce-popover.ce-toolbox.opened"
CAP = Path("experiments/03-vc-editor/capture")


def report_blocks(page, tag):
    info = page.evaluate("""() => [...document.querySelectorAll('.codex-editor .ce-block')].map(b => {
        const c = b.querySelector('.ce-block__content');
        const first = c && c.firstElementChild;
        const deep = c && c.querySelector('ul,ol,[class*=editor-][class*=-tool]');
        return {
            firstChildTag: first ? first.tagName : null,
            firstChildCls: first ? first.className : null,
            deepTag: deep ? deep.tagName : null,
            deepCls: deep ? deep.className : null,
            text: (c ? c.innerText : '').slice(0,30),
        };
    }))""")
    print(f"[{tag}] blocks:", flush=True)
    for i, b in enumerate(info):
        print(f"   {i}: first={b['firstChildTag']}/{ascii(b['firstChildCls'] or '')[:40]} "
              f"deep={b['deepTag']}/{ascii(b['deepCls'] or '')[:40]} text={ascii(b['text'])}", flush=True)
    return info


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
        page.click(TITLE_SEL); page.keyboard.type("PROBE v6 ol"); page.keyboard.press("Enter")
        time.sleep(0.6)
        try:
            page.click(".ce-toolbar__plus", timeout=4000)
        except Exception:
            page.eval_on_selector(".ce-toolbar__plus", "el=>el.click()")
        page.wait_for_selector(TOOLBOX_OPEN_SEL, timeout=8000)
        page.eval_on_selector('.ce-toolbox__item[data-type="list"]', "el=>el.click()")
        time.sleep(0.7)
        page.keyboard.type("alpha"); page.keyboard.press("Enter"); page.keyboard.type("beta")
        time.sleep(0.4)
        report_blocks(page, "before")

        page.evaluate("""() => {
            const ul=document.querySelector('ul, ol');
            ul.closest('.ce-block').querySelector('.ce-block-action__settings-toggler').click();
        }""")
        time.sleep(0.8)
        clicked = page.evaluate(r"""() => {
            const it=[...document.querySelectorAll('.ce-block-settings__item')].find(e=>/Нумерованный/i.test(e.innerText||''));
            if(it){it.click(); return true;} return false;
        }""")
        print("clicked Нумерованный:", clicked, flush=True)
        time.sleep(1.5)   # let the re-render settle; NO Escape
        report_blocks(page, "after")
        (CAP / "v6_after_full.html").write_text(
            page.eval_on_selector(".codex-editor", "el=>el.outerHTML"), encoding="utf-8")
        page.screenshot(path=str(CAP / "v6_after.png"))
        print("PROBE v6 DONE. Browser open ~3 min. Look at the list in the window.", flush=True)
        time.sleep(180)
        ctx.close()


if __name__ == "__main__":
    main()

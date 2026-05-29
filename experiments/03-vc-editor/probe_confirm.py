"""Discovery probe v4 (Task 6): CONFIRM the full list+quote gestures end-to-end.

Confirms:
1. Ordered toggle: gear -> click the plugin tune "Нумерованный" turns <ul> into <ol>.
2. Inter-block transitions: how to leave a list / a quote and reach a fresh block
   where the toolbox "+" is usable for the next block.
3. Final block sequence (ordered list, then quote, then a paragraph).

Strategy for opening the toolbox after a custom block: prefer page.click on the
"+", but fall back to a JS .click() that bypasses hover-visibility.
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
    (CAP / f"v4_{label}.html").write_text(html, encoding="utf-8")
    try:
        page.screenshot(path=str(CAP / f"v4_{label}.png"))
    except Exception:
        pass
    print(f"[dump] {label}: {len(html)}b", flush=True)


def open_toolbox(page):
    """Open the add-block toolbox; fall back to JS click if the + is 'not visible'."""
    try:
        page.click(".ce-toolbar__plus", timeout=4000)
    except Exception:
        page.eval_on_selector(".ce-toolbar__plus", "el => el.click()")
    page.wait_for_selector(TOOLBOX_OPEN_SEL, timeout=8000)


def block_types(page):
    """Return the tool class of each .ce-block in order."""
    return page.eval_on_selector_all(
        ".codex-editor .ce-block",
        """els => els.map(b => {
            const c = b.querySelector('.ce-block__content > div > div, .ce-block__content > div');
            const tool = b.querySelector('[class*=editor-][class*=-tool]');
            return tool ? (tool.className.match(/editor-[a-z]+-tool/)||['?'])[0] : 'text?';
        })""",
    )


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
        page.keyboard.type("PROBE v4 confirm")
        page.keyboard.press("Enter")
        time.sleep(0.6)

        # ---- ordered LIST ----
        open_toolbox(page)
        page.eval_on_selector('.ce-toolbox__item[data-type="list"]', "el => el.click()")
        time.sleep(0.7)
        page.keyboard.type("alpha")
        page.keyboard.press("Enter")
        page.keyboard.type("beta")
        time.sleep(0.3)
        print("tag before toggle:", page.eval_on_selector(".editor-list-tool", "e=>e.tagName"), flush=True)

        # open gear, click the "Нумерованный" plugin tune
        page.evaluate("""() => {
            const t=document.querySelector('.editor-list-tool');
            const g=t.closest('.ce-block').querySelector('.ce-block-action__settings-toggler');
            g.click();
        }""")
        time.sleep(0.7)
        res = page.evaluate(r"""() => {
            const items=[...document.querySelectorAll('.ce-block-settings__plugin .ce-block-settings__item, .ce-block-settings__item')];
            const labels=items.map(e=>(e.innerText||'').trim());
            const ord=items.find(e=>/Нумерованный/i.test(e.innerText||''));
            if(ord){ord.click(); return {clicked:true, labels};}
            return {clicked:false, labels};
        }""")
        print("toggle:", res, flush=True)
        time.sleep(0.7)
        page.keyboard.press("Escape")
        time.sleep(0.3)
        tag_after = page.eval_on_selector(".editor-list-tool", "e=>e.tagName")
        print("tag AFTER toggle:", tag_after, flush=True)   # expect OL
        dump(page, "10_ordered_list")

        # ---- leave list -> need a fresh block. Click end of last li, Enter x2 ----
        page.eval_on_selector(".editor-list-tool", "el => { const r=document.createRange(); r.selectNodeContents(el.lastElementChild||el); r.collapse(false); const s=getSelection(); s.removeAllRanges(); s.addRange(r); el.focus(); }")
        page.keyboard.press("Enter")
        time.sleep(0.2)
        page.keyboard.press("Enter")
        time.sleep(0.4)
        print("types after leaving list:", block_types(page), flush=True)

        # ---- QUOTE ----
        open_toolbox(page)
        page.eval_on_selector('.ce-toolbox__item[data-type="quote"]', "el => el.click()")
        time.sleep(0.7)
        # type into the large body field explicitly
        page.eval_on_selector(".ce-block--focused .editor-quote-tool .editor-tool-input--text-lg, .editor-quote-tool .editor-tool-input--text-lg", "el => el.focus()")
        page.keyboard.type("the quote body")
        time.sleep(0.3)
        dump(page, "20_quote")

        # ---- leave quote -> fresh block. Try ArrowDown then Enter, else click below ----
        page.keyboard.press("Enter")
        time.sleep(0.2)
        page.keyboard.press("Enter")
        time.sleep(0.3)
        print("types after leaving quote:", block_types(page), flush=True)

        # ---- a trailing paragraph to prove flow continues ----
        try:
            open_toolbox(page)
            page.keyboard.press("Escape")  # close toolbox; we just want a text block
        except Exception:
            pass
        page.keyboard.type("trailing paragraph")
        time.sleep(0.3)
        dump(page, "30_final")
        print("FINAL block types:", block_types(page), flush=True)

        print("PROBE v4 DONE. Browser open ~4 min. URL:", page.url, flush=True)
        time.sleep(240)
        ctx.close()


if __name__ == "__main__":
    main()

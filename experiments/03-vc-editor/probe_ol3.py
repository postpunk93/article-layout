"""Probe v7 (Task 6): dead-simple. Insert list, toggle 'Нумерованный', wait,
save full editor HTML + screenshot. No fancy evaluate (avoids JS syntax pitfalls).
"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".vc-profile"
EDITOR_URL = "https://vc.ru/?modal=editor"
TITLE_SEL = 'div.editor-tool-input[data-placeholder="Заголовок"]'
TOOLBOX_OPEN_SEL = ".ce-popover.ce-toolbox.opened"
CAP = Path("experiments/03-vc-editor/capture")

GEAR_CLICK = """() => {
  const ul = document.querySelector('ul, ol');
  if (!ul) return 'no-list';
  ul.closest('.ce-block').querySelector('.ce-block-action__settings-toggler').click();
  return 'ok';
}"""

TUNE_CLICK = """() => {
  const items = Array.from(document.querySelectorAll('.ce-block-settings__item'));
  const it = items.find(e => (e.innerText || '').indexOf('Нумерованный') >= 0);
  if (!it) return 'no-tune';
  it.click();
  return 'ok';
}"""


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
        page.click(TITLE_SEL); page.keyboard.type("PROBE v7 ol"); page.keyboard.press("Enter")
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
        CAP.mkdir(parents=True, exist_ok=True)
        (CAP / "v7_before.html").write_text(
            page.eval_on_selector(".codex-editor", "el=>el.outerHTML"), encoding="utf-8")
        print("gear:", page.evaluate(GEAR_CLICK), flush=True)
        time.sleep(0.8)
        print("tune:", page.evaluate(TUNE_CLICK), flush=True)
        time.sleep(2.0)   # settle; NO Escape
        (CAP / "v7_after.html").write_text(
            page.eval_on_selector(".codex-editor", "el=>el.outerHTML"), encoding="utf-8")
        page.screenshot(path=str(CAP / "v7_after.png"))
        print("PROBE v7 DONE. Browser open ~3 min — eyeball the list (numbered?).", flush=True)
        time.sleep(180)
        ctx.close()


if __name__ == "__main__":
    main()

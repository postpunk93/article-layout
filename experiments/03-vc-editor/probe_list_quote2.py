"""Discovery probe v2 for VC Editor.js LIST + QUOTE (Task 6, refined).

Learnings from v1:
- List block is a single contenteditable: <ul class="editor-list-tool"><li>..</li></ul>.
  Items created by typing + Enter; exit via Enter on an empty trailing <li>.
- Block settings gear is `.ce-block-action__settings-toggler` (inside
  `.ce-block__actions`), NOT `.ce-toolbar__settings-btn`.
- v1's quote step failed because the "+" wasn't visible after the list. So here
  QUOTE is probed FIRST (from a fresh empty block, the known-good path).

Goal: capture (a) quote block field structure + exit gesture, and (b) the list
block-settings popover that should expose ordered/unordered.
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
        html = f"<no .codex-editor: {e}>"
    (CAP / f"v2_{label}.html").write_text(html, encoding="utf-8")
    try:
        page.screenshot(path=str(CAP / f"v2_{label}.png"))
    except Exception:
        pass
    print(f"[dump] {label}: {len(html)} bytes", flush=True)


def open_toolbox(page):
    page.click(".ce-toolbar__plus", timeout=8000)
    page.wait_for_selector(TOOLBOX_OPEN_SEL, timeout=8000)


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        print(f"Opening {EDITOR_URL}", flush=True)
        page.goto(EDITOR_URL)
        try:
            page.wait_for_selector(TITLE_SEL, timeout=30000)
        except Exception:
            print("!! not logged in; leaving window open", flush=True)
            time.sleep(300); ctx.close(); return
        time.sleep(2)
        page.click(TITLE_SEL)
        page.keyboard.type("PROBE v2 quote+list")
        page.keyboard.press("Enter")
        time.sleep(0.6)
        dump(page, "00_seeded")

        # =========================== QUOTE FIRST ===========================
        try:
            open_toolbox(page)
            page.eval_on_selector('.ce-toolbox__item[data-type="quote"]', "el => el.click()")
            time.sleep(0.8)
            dump(page, "20_quote_inserted")
            # enumerate editable fields in the focused quote block
            fields = page.eval_on_selector_all(
                ".ce-block--focused [contenteditable], .ce-block--focused .cdx-input, "
                ".ce-block--focused input, .ce-block--focused textarea",
                "els => els.map(e => ({tag:e.tagName.toLowerCase(), cls:e.className, "
                "ph:e.getAttribute('data-placeholder')||e.getAttribute('placeholder'), "
                "ce:e.getAttribute('contenteditable')}))",
            )
            print("QUOTE FIELDS (empty):", fields, flush=True)
            (CAP / "v2_quote_fields.txt").write_text(str(fields), encoding="utf-8")

            page.keyboard.type("the quote body text")
            time.sleep(0.4)
            dump(page, "21_quote_typed")
            # single Enter — does it stay in quote (newline) or exit?
            page.keyboard.press("Enter")
            time.sleep(0.4)
            dump(page, "22_quote_one_enter")
            # second Enter
            page.keyboard.press("Enter")
            time.sleep(0.4)
            dump(page, "23_quote_two_enter")
            nblocks = page.eval_on_selector_all(".codex-editor .ce-block", "els => els.length")
            print("blocks after quote exit:", nblocks, flush=True)
        except Exception as e:
            print("QUOTE probe failed:", e, flush=True)
            dump(page, "2X_quote_failed")

        # ensure a fresh empty focused block for the list: click the last text tool
        try:
            page.eval_on_selector_all(
                ".editor-text-tool", "els => { if (els.length) els[els.length-1].focus(); }"
            )
            page.locator(".editor-text-tool").last.click()
            time.sleep(0.3)
        except Exception as e:
            print("refocus before list failed:", e, flush=True)

        # =========================== LIST ===========================
        try:
            open_toolbox(page)
            page.eval_on_selector('.ce-toolbox__item[data-type="list"]', "el => el.click()")
            time.sleep(0.8)
            dump(page, "10_list_inserted")
            page.keyboard.type("alpha")
            page.keyboard.press("Enter")
            page.keyboard.type("beta")
            page.keyboard.press("Enter")
            page.keyboard.type("gamma")
            time.sleep(0.4)
            dump(page, "11_list_three_items")

            # --- open block settings (gear) for the focused list block ---
            opened = False
            for sel in [
                ".ce-block--focused .ce-block-action__settings-toggler",
                ".ce-toolbar .ce-block-action__settings-toggler",
                ".ce-block-action__settings-toggler",
            ]:
                try:
                    page.eval_on_selector(sel, "el => el.click()")
                    time.sleep(0.6)
                    opened = True
                    print("settings opened via:", sel, flush=True)
                    break
                except Exception:
                    continue
            # dump every popover/settings container + enumerate items
            pops = page.eval_on_selector_all(
                ".ce-popover, .ce-settings, [class*='settings'], [class*='tune']",
                "els => els.map(e => e.outerHTML)",
            )
            (CAP / "v2_list_settings_popover.html").write_text(
                "\n\n=====\n\n".join(pops), encoding="utf-8")
            items = page.eval_on_selector_all(
                ".ce-popover__item, .ce-settings__button, .cdx-settings-button, "
                ".ce-popover-item",
                "els => els.map(e => ({text:(e.innerText||'').trim(), "
                "cls:e.className, name:e.dataset.itemName||null, "
                "data:Object.assign({},e.dataset), aria:e.getAttribute('aria-label')}))",
            )
            print("LIST SETTINGS ITEMS:", items, flush=True)
            (CAP / "v2_list_settings_items.txt").write_text(str(items), encoding="utf-8")
            dump(page, "12_list_settings_open")
        except Exception as e:
            print("LIST probe failed:", e, flush=True)
            dump(page, "1X_list_failed")

        dump(page, "99_final")
        print("PROBE v2 DONE. Browser open ~5 min. URL:", page.url, flush=True)
        time.sleep(300)
        ctx.close()


if __name__ == "__main__":
    main()

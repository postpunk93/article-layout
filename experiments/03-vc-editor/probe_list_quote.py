"""Discovery probe for VC's Editor.js LIST and QUOTE tools (Task 6).

Usage: python -m experiments.03-vc-editor.probe_list_quote
  (or:  python experiments/03-vc-editor/probe_list_quote.py)

Opens the editor in the persistent .vc-profile (headed), then drives the list
and quote tools step by step, dumping the live DOM + a screenshot after each
step into experiments/03-vc-editor/capture/ so the controller can read the real
selectors/gestures. Defensive: every step is wrapped so a failure still dumps
what's on screen. Keeps the browser open at the end for manual inspection.

NEVER clicks Publish. Stops at whatever draft state it reaches.
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
    """Write current editor HTML + a screenshot tagged with `label`."""
    CAP.mkdir(parents=True, exist_ok=True)
    try:
        html = page.eval_on_selector(".codex-editor", "el => el.outerHTML")
    except Exception as e:
        html = f"<no .codex-editor: {e}>"
    (CAP / f"probe_{label}.html").write_text(html, encoding="utf-8")
    try:
        page.screenshot(path=str(CAP / f"probe_{label}.png"))
    except Exception:
        pass
    print(f"[dump] {label}: {len(html)} bytes", flush=True)


def dump_popover(page, label):
    """Dump any open popover (toolbox or block-settings tune menu)."""
    try:
        pops = page.eval_on_selector_all(
            ".ce-popover, .ce-settings, .ce-toolbar__settings-btn ~ *",
            "els => els.map(e => e.outerHTML)",
        )
    except Exception as e:
        pops = [f"<err: {e}>"]
    (CAP / f"probe_{label}_popover.html").write_text(
        "\n\n=====\n\n".join(pops), encoding="utf-8"
    )
    print(f"[dump] {label}_popover: {len(pops)} popovers", flush=True)


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

        # --- confirm we're logged in / editor opened ---
        try:
            page.wait_for_selector(TITLE_SEL, timeout=30000)
        except Exception:
            print("!! Title block not found in 30s. Are we logged in? "
                  "Log in by hand in the open window; leaving it open.", flush=True)
            time.sleep(600)
            ctx.close()
            return
        time.sleep(2)
        print("Editor open.", flush=True)

        # --- seed: title + an empty body block ---
        page.click(TITLE_SEL)
        page.keyboard.type("PROBE list+quote")
        page.keyboard.press("Enter")
        time.sleep(0.6)
        dump(page, "00_seeded")

        # --- toolbox contents (reconfirm list/quote present) ---
        try:
            open_toolbox(page)
            items = page.eval_on_selector_all(
                ".ce-toolbox__item",
                "els => els.map(e => ({type: e.dataset.type, text: (e.innerText||'').trim()}))",
            )
            print("TOOLBOX ITEMS:", items, flush=True)
            (CAP / "probe_toolbox_items.txt").write_text(str(items), encoding="utf-8")
        except Exception as e:
            print("toolbox dump failed:", e, flush=True)

        # =========================== LIST ===========================
        try:
            # toolbox is open from above; click the list tool
            page.eval_on_selector('.ce-toolbox__item[data-type="list"]', "el => el.click()")
            time.sleep(0.8)
            dump(page, "10_list_inserted")

            # type two items
            page.keyboard.type("first item")
            time.sleep(0.3)
            page.keyboard.press("Enter")
            page.keyboard.type("second item")
            time.sleep(0.3)
            dump(page, "11_list_two_items")

            # open block settings (tune menu) to find ordered/unordered toggle.
            # The gear lives in .ce-toolbar; hovering the block reveals it.
            try:
                page.eval_on_selector(".ce-toolbar__settings-btn", "el => el.click()")
                time.sleep(0.6)
                dump_popover(page, "12_list_settings")
                dump(page, "12_list_settings_full")
                # enumerate settings items so we can see ordered/unordered labels
                tunes = page.eval_on_selector_all(
                    ".ce-popover__item, .ce-settings__button, .cdx-settings-button",
                    "els => els.map(e => ({text:(e.innerText||'').trim(), cls:e.className, data:Object.assign({},e.dataset), aria:e.getAttribute('aria-label')}))",
                )
                print("LIST TUNES:", tunes, flush=True)
                (CAP / "probe_list_tunes.txt").write_text(str(tunes), encoding="utf-8")
                page.keyboard.press("Escape")
                time.sleep(0.3)
            except Exception as e:
                print("list settings probe failed:", e, flush=True)

            # try to EXIT the list: Enter on an empty item (double-Enter)
            page.keyboard.press("Enter")
            time.sleep(0.2)
            page.keyboard.press("Enter")
            time.sleep(0.4)
            dump(page, "13_list_after_double_enter")
        except Exception as e:
            print("LIST probe failed:", e, flush=True)
            dump(page, "1X_list_failed")

        # =========================== QUOTE ===========================
        try:
            # ensure we're on an empty block; open toolbox and click quote
            open_toolbox(page)
            page.eval_on_selector('.ce-toolbox__item[data-type="quote"]', "el => el.click()")
            time.sleep(0.8)
            dump(page, "20_quote_inserted")

            page.keyboard.type("the quote body text")
            time.sleep(0.3)
            dump(page, "21_quote_typed")

            # is there a second field (author/caption)? dump all editable fields
            try:
                fields = page.eval_on_selector_all(
                    ".ce-block--focused [contenteditable], .cdx-quote *[contenteditable], .cdx-input",
                    "els => els.map(e => ({cls:e.className, ph:e.getAttribute('data-placeholder')||e.getAttribute('placeholder'), text:(e.innerText||'').trim().slice(0,40)}))",
                )
                print("QUOTE FIELDS:", fields, flush=True)
                (CAP / "probe_quote_fields.txt").write_text(str(fields), encoding="utf-8")
            except Exception as e:
                print("quote fields probe failed:", e, flush=True)

            # try to exit quote
            page.keyboard.press("Enter")
            time.sleep(0.2)
            page.keyboard.press("Enter")
            time.sleep(0.4)
            dump(page, "22_quote_after_double_enter")
        except Exception as e:
            print("QUOTE probe failed:", e, flush=True)
            dump(page, "2X_quote_failed")

        dump(page, "99_final")
        print("PROBE DONE. Browser stays open ~8 min for inspection. "
              "URL:", page.url, flush=True)
        time.sleep(480)
        ctx.close()


if __name__ == "__main__":
    main()

"""Confirm how a Pikabu draft is saved + what signal we can detect.

Sets a title + a little body, clicks «Сохранить черновик», and captures: the
save network request(s), any toast/confirmation text, the URL, and the enabled
state / text of the draft button before and after. Helps the adapter detect a
successful save.

Writes experiments/04-pikabu-editor/probe_draft.json (UTF-8). Non-interactive.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
ADD_URL = "https://pikabu.ru/add"
TITLE_SEL = 'textarea[placeholder="Заголовок"]'
BODY_SEL = ".tiptap.ProseMirror"
SAVE_TEXT = "Сохранить черновик"
OUT = Path("experiments/04-pikabu-editor/probe_draft.json")


def main():
    report = {"requests": []}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            try:
                u = resp.url
                if any(k in u.lower() for k in ("draft", "save", "story", "post")) and "pikabu.ru" in u:
                    report["requests"].append({"status": resp.status, "method": resp.request.method, "url": u[:160]})
            except Exception:
                pass

        page.on("response", on_response)

        page.goto(ADD_URL, wait_until="domcontentloaded")
        page.wait_for_selector(BODY_SEL, timeout=30000)
        page.wait_for_timeout(2500)

        page.click(TITLE_SEL)
        page.keyboard.type("Черновик-проба")
        page.click(BODY_SEL)
        page.keyboard.type("Текст тела для проверки сохранения черновика.")
        page.wait_for_timeout(800)

        # Inspect all buttons whose text mentions draft/publish (so we click the right one).
        report["buttons"] = page.evaluate(
            """() => [...document.querySelectorAll('button')]
                .map(b => ({text: (b.innerText||'').trim().slice(0,30),
                            disabled: b.disabled,
                            dataTest: b.getAttribute('data-test')}))
                .filter(b => /чернов|опубл|публик|сохран/i.test(b.text) || /draft|publish/i.test(b.dataTest||''))"""
        )

        report["url_before"] = page.url
        n_req_before = len(report["requests"])
        try:
            page.locator(f"button:has-text('{SAVE_TEXT}')").first.click(timeout=8000)
            report["clicked"] = True
        except Exception as e:
            report["clicked"] = f"ERROR: {str(e)[:100]}"
        page.wait_for_timeout(4000)
        report["url_after"] = page.url

        # Any toast / notification text that appeared.
        report["toasts"] = page.evaluate(
            """() => [...document.querySelectorAll(
                '[class*=toast], [class*=notify], [class*=notification], [class*=snackbar], [role=alert]'
            )].map(el => (el.innerText||'').trim().slice(0,80)).filter(Boolean)"""
        )
        report["requests_during_save"] = report["requests"][n_req_before:]

        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Wrote", OUT)
        print("buttons:", json.dumps(report["buttons"], ensure_ascii=False))
        print("clicked:", report["clicked"])
        print("url_before:", report["url_before"], "-> url_after:", report["url_after"])
        print("toasts:", json.dumps(report["toasts"], ensure_ascii=False))
        print("requests_during_save:", json.dumps(report["requests_during_save"], ensure_ascii=False))
        ctx.close()


if __name__ == "__main__":
    main()

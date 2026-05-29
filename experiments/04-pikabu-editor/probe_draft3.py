"""Find WHERE a saved Pikabu draft lives (it doesn't restore on /add reload).

Saves a uniquely-marked draft, then: dumps any draft-ish links/menu items, and
probes candidate draft-list URLs for the mark.

Writes experiments/04-pikabu-editor/probe_draft3.json (UTF-8). Non-interactive.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
ADD_URL = "https://pikabu.ru/add"
TITLE_SEL = 'textarea[placeholder="Заголовок"]'
BODY_SEL = ".tiptap.ProseMirror"
SAVE_TEXT = "Сохранить черновик"
MARK = "DRAFTPROBE-Q3"
OUT = Path("experiments/04-pikabu-editor/probe_draft3.json")
CANDIDATES = [
    "https://pikabu.ru/drafts",
    "https://pikabu.ru/draft",
    "https://pikabu.ru/@me/drafts",
]


def main():
    report = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(ADD_URL, wait_until="domcontentloaded")
        page.wait_for_selector(BODY_SEL, timeout=30000)
        page.wait_for_timeout(2500)

        page.click(TITLE_SEL)
        page.keyboard.type(f"Заголовок {MARK}")
        page.click(BODY_SEL)
        page.keyboard.type(f"Тело {MARK}.")
        page.wait_for_timeout(800)
        try:
            with page.expect_response(lambda r: "save_draft_post" in r.url, timeout=10000) as resp:
                page.locator(f"button:has-text('{SAVE_TEXT}')").first.click(timeout=8000)
            report["save_status"] = resp.value.status
        except Exception as e:
            report["save_status"] = f"ERROR: {str(e)[:100]}"
        page.wait_for_timeout(3000)

        # Draft-ish links anywhere on the editor page (e.g. opened a menu).
        report["draft_links"] = page.evaluate(
            """() => [...document.querySelectorAll('a[href]')]
                .map(a => ({text: (a.innerText||'').trim().slice(0,30), href: a.getAttribute('href')}))
                .filter(a => /чернов|draft/i.test(a.text) || /draft|чернов/i.test(a.href||''))
                .slice(0, 20)"""
        )

        # Probe candidate draft-list URLs for the mark.
        report["candidates"] = []
        for url in CANDIDATES:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(2500)
                body = page.evaluate("() => document.body.innerText.slice(0, 4000)")
                report["candidates"].append({
                    "url": url,
                    "final_url": page.url,
                    "has_mark": MARK in body,
                    "snippet": body[:200],
                })
            except Exception as e:
                report["candidates"].append({"url": url, "error": str(e)[:100]})

        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Wrote", OUT)
        print("save_status:", report["save_status"])
        print("draft_links:", json.dumps(report["draft_links"], ensure_ascii=False))
        for c in report["candidates"]:
            print("cand:", c.get("url"), "->", c.get("final_url"), "has_mark:", c.get("has_mark"), "err:", c.get("error"))
        ctx.close()


if __name__ == "__main__":
    main()

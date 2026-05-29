"""Verify a saved Pikabu draft actually PERSISTS across a reload.

Types a uniquely-marked title + body, clicks «Сохранить черновик», waits for the
save_draft_post response, then reloads /add and reports whether the editor
restored the content (proving the draft persisted) — and how long it took.

Writes experiments/04-pikabu-editor/probe_draft2.json (UTF-8). Non-interactive.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
ADD_URL = "https://pikabu.ru/add"
TITLE_SEL = 'textarea[placeholder="Заголовок"]'
BODY_SEL = ".tiptap.ProseMirror"
SAVE_TEXT = "Сохранить черновик"
MARK = "DRAFTPROBE-Z7"
OUT = Path("experiments/04-pikabu-editor/probe_draft2.json")


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
        page.keyboard.type(f"Тело черновика {MARK} для проверки персистентности.")
        page.wait_for_timeout(800)

        try:
            with page.expect_response(lambda r: "save_draft_post" in r.url, timeout=10000) as resp:
                page.locator(f"button:has-text('{SAVE_TEXT}')").first.click(timeout=8000)
            report["save_status"] = resp.value.status
        except Exception as e:
            report["save_status"] = f"ERROR: {str(e)[:100]}"
        page.wait_for_timeout(3000)

        # Reload a fresh /add and see whether the draft content comes back.
        page.goto(ADD_URL, wait_until="domcontentloaded")
        page.wait_for_selector(BODY_SEL, timeout=30000)
        page.wait_for_timeout(4000)
        state = page.evaluate(
            """(mark) => {
                const title = document.querySelector('textarea[placeholder="Заголовок"]');
                const body = document.querySelector('.tiptap.ProseMirror');
                const tv = title ? (title.value||'') : '';
                const bv = body ? (body.innerText||'') : '';
                return {
                    title_value: tv.slice(0,60),
                    body_text: bv.slice(0,80),
                    title_has_mark: tv.includes(mark),
                    body_has_mark: bv.includes(mark),
                };
            }""",
            MARK,
        )
        report["after_reload"] = state
        # Some editors show a "restore draft?" prompt instead of auto-filling.
        report["restore_prompt"] = page.evaluate(
            """() => [...document.querySelectorAll('button, [role=button]')]
                .map(b => (b.innerText||'').trim())
                .filter(t => /восстанов|продолж|чернов|восстановить/i.test(t)).slice(0,5)"""
        )

        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Wrote", OUT)
        print("save_status:", report["save_status"])
        print("after_reload:", json.dumps(report["after_reload"], ensure_ascii=False))
        print("restore_prompt:", json.dumps(report["restore_prompt"], ensure_ascii=False))
        ctx.close()


if __name__ == "__main__":
    main()

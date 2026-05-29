"""After clicking floating + -> photo, dump what appears (modal/dropzone/file input).

Writes experiments/04-pikabu-editor/probe_image4.json (UTF-8). Non-interactive.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
ADD_URL = "https://pikabu.ru/add"
BODY_SEL = ".tiptap.ProseMirror"
FLOATING_SEL = ".floating-menu-view__button--HzqgG6Ir"
MENU_BTN_SEL = ".floating-menu-view__menuButton--MJpEPZAY"
OUT = Path("experiments/04-pikabu-editor/probe_image4.json")


def photo_button(page):
    for b in page.query_selector_all(MENU_BTN_SEL):
        u = b.query_selector("use")
        href = u.get_attribute("xlink:href") or u.get_attribute("href") or "" if u else ""
        if "photo" in href:
            return b
    return None


def snapshot(page):
    return page.evaluate(
        """() => ({
            file_inputs: [...document.querySelectorAll('input[type=file]')].map(el => ({
                accept: el.getAttribute('accept'),
                cls: (el.className||'').toString().slice(0,60),
                multiple: el.hasAttribute('multiple'),
                parentCls: (el.parentElement?.className||'').toString().slice(0,60),
            })),
            modals: [...document.querySelectorAll(
                '[class*=modal], [role=dialog], [class*=dialog], [class*=upload], [class*=dropzone]'
            )].filter(el => el.getBoundingClientRect().width>0).map(el => ({
                cls: (el.className||'').toString().slice(0,80),
                text: (el.innerText||'').trim().slice(0,80),
            })),
        })"""
    )


def main():
    report = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(ADD_URL, wait_until="domcontentloaded")
        page.wait_for_selector(BODY_SEL, timeout=30000)
        page.wait_for_timeout(3000)

        page.click(BODY_SEL)
        page.wait_for_timeout(300)
        report["before"] = snapshot(page)

        page.click(FLOATING_SEL)
        page.wait_for_timeout(600)
        btn = photo_button(page)
        btn.click()
        page.wait_for_timeout(1500)
        report["after_photo_click"] = snapshot(page)

        # Also dump any newly inserted node in the editor (empty image placeholder?).
        report["editor_tail_html"] = page.evaluate(
            f"""() => {{
                const root = document.querySelector('{BODY_SEL}');
                const last = root.lastElementChild;
                return last ? last.outerHTML.slice(0,1200) : null;
            }}"""
        )
        # Full page file-input count + any element with 'photo'/'image' in data-test.
        report["photo_related"] = page.evaluate(
            """() => [...document.querySelectorAll('[data-test]')]
                .map(el => el.getAttribute('data-test'))
                .filter(dt => /photo|image|media|upload/i.test(dt||''))"""
        )

        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Wrote", OUT)
        print("file_inputs before:", len(report["before"]["file_inputs"]),
              "after:", len(report["after_photo_click"]["file_inputs"]))
        print("after file_inputs:", json.dumps(report["after_photo_click"]["file_inputs"], ensure_ascii=False))
        print("modals after:", json.dumps(report["after_photo_click"]["modals"], ensure_ascii=False))
        print("editor tail:", (report["editor_tail_html"] or "")[:300])
        ctx.close()


if __name__ == "__main__":
    main()

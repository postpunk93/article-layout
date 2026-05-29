"""Probe the Pikabu /add editor DOM under the saved login. Non-interactive.

Dumps candidate selectors for: title field, body editor, toolbar/insert
controls, file inputs. Run: python -m experiments.04-pikabu-editor.probe_add
(or: python experiments/04-pikabu-editor/probe_add.py)
"""
import json
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
ADD_URL = "https://pikabu.ru/add"


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(ADD_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        print("URL after load:", page.url)
        print("TITLE:", page.title())

        # Login state: is there a login form / are we redirected?
        body_text = page.evaluate("() => document.body.innerText.slice(0, 400)")
        print("\n--- BODY TEXT (first 400 chars) ---\n", body_text)

        # Candidate editable fields: inputs, textareas, contenteditables.
        fields = page.evaluate(
            """() => {
                const out = [];
                const els = document.querySelectorAll(
                  'input, textarea, [contenteditable="true"], [contenteditable=""]'
                );
                els.forEach(el => {
                    const r = el.getBoundingClientRect();
                    out.push({
                        tag: el.tagName.toLowerCase(),
                        type: el.getAttribute('type'),
                        placeholder: el.getAttribute('placeholder')
                            || el.getAttribute('data-placeholder'),
                        ariaLabel: el.getAttribute('aria-label'),
                        cls: el.getAttribute('class'),
                        contenteditable: el.getAttribute('contenteditable'),
                        name: el.getAttribute('name'),
                        visible: r.width > 0 && r.height > 0,
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                });
                return out;
            }"""
        )
        print("\n--- EDITABLE FIELDS (", len(fields), ") ---")
        for f in fields:
            print(json.dumps(f, ensure_ascii=False))

        # File inputs (image upload).
        files = page.evaluate(
            """() => [...document.querySelectorAll('input[type=file]')].map(el => ({
                accept: el.getAttribute('accept'),
                cls: el.getAttribute('class'),
                multiple: el.hasAttribute('multiple'),
                name: el.getAttribute('name'),
            }))"""
        )
        print("\n--- FILE INPUTS (", len(files), ") ---")
        for f in files:
            print(json.dumps(f, ensure_ascii=False))

        # Buttons / toolbar controls with their labels.
        buttons = page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('button, [role=button], a.button, .button').forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) return;
                    out.push({
                        tag: el.tagName.toLowerCase(),
                        text: (el.innerText || '').trim().slice(0, 40),
                        title: el.getAttribute('title'),
                        ariaLabel: el.getAttribute('aria-label'),
                        cls: (el.getAttribute('class') || '').slice(0, 80),
                    });
                });
                return out;
            }"""
        )
        print("\n--- VISIBLE BUTTONS (", len(buttons), ") ---")
        for b in buttons:
            print(json.dumps(b, ensure_ascii=False))

        ctx.close()


if __name__ == "__main__":
    main()

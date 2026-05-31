# src/_discover_habr.py  — THROWAWAY discovery probe (Task 2). Delete after use.
"""Phase-A discovery for the Habr adapter.

Opens a visible, persistent Chromium context on the Habr profile, lets you log in
and open the sandbox article editor by hand, then dumps what the adapter needs:
editor URL, editor framework, title/body selectors, and the toolbar map.

Run it yourself (interactive):
    ! python -m src._discover_habr            # client defaults to "default"
    ! python -m src._discover_habr <client>

Nothing here is wired into the app; it only reads the page. Findings go into
docs/platform-notes.md, then this file is deleted.
"""
import sys

from playwright.sync_api import sync_playwright

from src import sessions

# Best guess; if it's wrong just navigate to the editor by hand before pressing Enter.
START_URL = "https://habr.com/ru/sandbox/add/"

INSPECT_JS = r"""
() => {
  const out = {};
  out.url = location.href;
  out.docTitle = document.title;

  // --- framework signals ---
  out.framework = {
    prosemirror: !!document.querySelector('.ProseMirror'),
    tiptap: !!document.querySelector('.tiptap'),
    editorjs: !!document.querySelector('.codex-editor, .ce-block'),
    ckeditor: !!document.querySelector('.ck-editor, .ck-content'),
    quill: !!document.querySelector('.ql-editor'),
    draftjs: !!document.querySelector('.public-DraftEditor-content'),
  };

  const desc = (el) => el ? {
    tag: el.tagName.toLowerCase(),
    cls: el.getAttribute('class'),
    dataTest: el.getAttribute('data-test'),
    placeholder: el.getAttribute('placeholder') || el.getAttribute('data-placeholder'),
    ariaLabel: el.getAttribute('aria-label'),
    id: el.id || null,
  } : null;

  // --- title candidates: textareas/inputs + contenteditable that look like a heading ---
  out.textInputs = [...document.querySelectorAll('input, textarea')]
    .map(desc)
    .filter(d => d.placeholder || (d.cls && /title|head|name|theme/i.test(d.cls)));

  // --- contenteditable candidates (body + maybe title) ---
  out.contentEditables = [...document.querySelectorAll('[contenteditable="true"]')]
    .slice(0, 12)
    .map(el => ({...desc(el), textLen: (el.textContent || '').length}));

  // --- toolbar / control map: buttons & role=button with any stable handle ---
  const seen = new Set();
  out.controls = [...document.querySelectorAll('button, [role="button"], [data-test]')]
    .map(el => ({
      tag: el.tagName.toLowerCase(),
      dataTest: el.getAttribute('data-test'),
      ariaLabel: el.getAttribute('aria-label'),
      title: el.getAttribute('title'),
      text: (el.textContent || '').trim().slice(0, 40),
      cls: (el.getAttribute('class') || '').slice(0, 60),
    }))
    .filter(c => {
      const key = JSON.stringify(c);
      if (seen.has(key)) return false;
      seen.add(key);
      return c.dataTest || c.ariaLabel || c.title || c.text;
    })
    .slice(0, 80);

  return out;
}
"""


def _dump(label, value):
    import json
    print(f"\n=== {label} ===")
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    client = sys.argv[1] if len(sys.argv) > 1 else "default"
    with sync_playwright() as p:
        # Standard launcher (now uses installed Chrome + anti-automation).
        ctx, page = sessions.open_context(p, client, "habr", headless=False)
        try:
            page.goto(START_URL, wait_until="domcontentloaded")
        except Exception as e:  # noqa: BLE001
            print(f"(goto {START_URL} failed: {e!r}) — navigate by hand instead.")
        print("\n" + "=" * 70)
        print("1) Log in to Habr if needed.")
        print("2) Open the SANDBOX article editor (the page with a Title field and")
        print("   an empty article body). Navigate by hand if the URL above was wrong.")
        print("3) Come back here and press Enter to inspect the page.")
        print("=" * 70)
        try:
            input("Press Enter once the editor is open... ")
        except EOFError:
            pass

        data = page.evaluate(INSPECT_JS)
        _dump("URL & framework", {"url": data["url"], "docTitle": data["docTitle"],
                                   "framework": data["framework"]})
        _dump("Text inputs (title candidates)", data["textInputs"])
        _dump("contenteditable candidates (body/title)", data["contentEditables"])
        _dump("Controls / toolbar map", data["controls"])
        print("\nCopy the above into the chat. Leave the browser open for phase B.")

        try:
            input("\nPress Enter to close the browser... ")
        except EOFError:
            pass
        ctx.close()


if __name__ == "__main__":
    main()

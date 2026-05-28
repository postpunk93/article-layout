"""Open VC in a persistent, visible browser and CONTINUOUSLY snapshot the DOM.

Usage: python -m src.discover_vc

Flow (no terminal interaction needed):
1. Launches a visible Chromium with a persistent profile (./.vc-profile).
2. Opens vc.ru. You log in by hand (first run only) and open the editor
   ("Написать" — it opens as a modal at https://vc.ru/?modal=editor).
3. Every 2 seconds the script picks the most "interesting" open tab (most
   form/editor elements) and writes a fresh snapshot to:
     experiments/03-vc-editor/capture/candidates.json (targeted selectors)
     experiments/03-vc-editor/capture/url.txt
   and, whenever that tab looks editor-like, also:
     experiments/03-vc-editor/capture/page.html
     experiments/03-vc-editor/capture/editor.png
   Writes are atomic (temp file + replace) so the reader never sees a
   half-written file.
4. Runs for up to TIMEOUT_SECONDS so we can inspect several states (empty
   editor, image dialog open, etc.). Stop it from the controller when done.

This deliberately does NOT rely on a correct "editor ready" heuristic — it
just keeps dumping the live DOM so the controller can read real selectors.
"""
import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE_DIR = ".vc-profile"
START_URL = "https://vc.ru/"
CAPTURE_DIR = Path("experiments/03-vc-editor/capture")
POLL_SECONDS = 2
TIMEOUT_SECONDS = 1200

_PROBE_JS = r"""
() => {
  const info = (el) => {
    const r = el.getBoundingClientRect();
    return {
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type'),
      id: el.id || null,
      name: el.getAttribute('name'),
      cls: el.getAttribute('class'),
      placeholder: el.getAttribute('placeholder'),
      aria: el.getAttribute('aria-label'),
      role: el.getAttribute('role'),
      contenteditable: el.getAttribute('contenteditable'),
      data: Object.assign({}, el.dataset),
      text: (el.innerText || '').trim().slice(0, 80),
      rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
    };
  };
  const pick = (sel) => Array.from(document.querySelectorAll(sel)).map(info);
  return {
    url: location.href,
    title: document.title,
    inputs: pick('input'),
    textareas: pick('textarea'),
    editables: pick('[contenteditable]'),
    fileInputs: pick('input[type=file]'),
    buttons: pick('button, [role=button]').filter(b => b.rect.w > 0).slice(0, 150),
  };
}
"""


def _atomic_write(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _score(probe):
    return (
        len(probe["inputs"]) + len(probe["textareas"])
        + len(probe["editables"]) + len(probe["fileInputs"])
    )


def _looks_editor(probe):
    return len(probe["editables"]) > 0 or len(probe["fileInputs"]) > 0


def main():
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(START_URL)
        print("Browser open. Log in and open the editor. Snapshotting every "
              f"{POLL_SECONDS}s for up to {TIMEOUT_SECONDS}s...", flush=True)

        waited = 0
        while waited < TIMEOUT_SECONDS:
            best = None
            for pg in list(ctx.pages):
                try:
                    probe = pg.evaluate(_PROBE_JS)
                except Exception:
                    continue
                if best is None or _score(probe) > _score(best[1]):
                    best = (pg, probe)
            if best is not None:
                pg, probe = best
                _atomic_write(CAPTURE_DIR / "url.txt", probe["url"] + "\n")
                _atomic_write(
                    CAPTURE_DIR / "candidates.json",
                    json.dumps(probe, ensure_ascii=False, indent=2),
                )
                if _looks_editor(probe):
                    try:
                        _atomic_write(CAPTURE_DIR / "page.html", pg.content())
                        pg.screenshot(path=str(CAPTURE_DIR / "editor.png"), full_page=True)
                    except Exception:
                        pass
                print(f"[{waited:4d}s] {probe['url']}  score={_score(probe)} "
                      f"editables={len(probe['editables'])} files={len(probe['fileInputs'])}",
                      flush=True)
            time.sleep(POLL_SECONDS)
            waited += POLL_SECONDS

        ctx.close()


if __name__ == "__main__":
    main()

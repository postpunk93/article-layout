"""Open Pikabu in a persistent, visible browser and keep it open for login.

Usage: python -m src.discover_pikabu
Log in by hand, navigate to the new-post page, then CLOSE the browser window to
finish (no terminal interaction needed — works even with no stdin). Cookies
persist in .pikabu-profile/ so later probes/adapter runs reuse the session.
"""
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".pikabu-profile"
PIKABU_URL = "https://pikabu.ru/"  # confirm exact new-post URL during discovery


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(PIKABU_URL)
        print(
            "Log in to Pikabu and open the new-post editor.\n"
            "When done, CLOSE the browser window to finish."
        )
        # Block until the user closes the browser (no stdin needed). When the
        # last page/window is closed, wait_for_timeout raises "Target closed".
        try:
            while ctx.pages:
                ctx.pages[0].wait_for_timeout(1000)
        except Exception:
            pass
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()

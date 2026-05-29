"""Open Pikabu in a persistent, visible browser and pause for manual inspection.

Usage: python -m src.discover_pikabu
Log in by hand if prompted, navigate to the new-post page, then use DevTools to
record selectors into experiments/04-pikabu-editor/notes.md. Press Enter in the
terminal to close. Cookies persist in .pikabu-profile/ for later runs.
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
        input("Inspect Pikabu, record selectors. Press Enter here to close...\n")
        ctx.close()


if __name__ == "__main__":
    main()

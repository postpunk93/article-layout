"""Open VC in a persistent, visible browser and pause for manual inspection.

Usage: python -m src.discover_vc

Log in by hand if prompted, navigate to the new-entry page, then use the
opened DevTools / page to record selectors into
experiments/03-vc-editor/notes.md. Press Enter in the terminal to close.
"""
from playwright.sync_api import sync_playwright

PROFILE_DIR = ".vc-profile"
VC_URL = "https://vc.ru/"  # confirm exact new-entry URL during discovery


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"]
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(VC_URL)
        input("Inspect VC, record selectors. Press Enter here to close...\n")
        ctx.close()


if __name__ == "__main__":
    main()

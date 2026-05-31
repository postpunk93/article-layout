# src/sessions.py
"""Single owner of browser-profile logic for the article-layout adapters.

A profile is a persistent Chromium context stored at
`.profiles/<client>/<platform>/`. The folder existing IS the fact that the
account is set up — there is no central registry. Per-profile metadata lives
in a `meta.json` beside the context. Liveness is never cached: `is_alive`
probes the live site every time.
"""
import json
import os
import subprocess
from pathlib import Path

from src import vc_adapter, pikabu_adapter, habr_adapter, smartlab_adapter, dzen_adapter

PROFILES_ROOT = Path(".profiles")

# All adapters drive the user's INSTALLED Chrome (channel="chrome"), not bundled
# Chromium: Habr's login is recognized only by the real Chrome reading its own
# profile (bundled Chromium can't decrypt Chrome's app-bound cookies). The
# automation switch is removed and navigator.webdriver masked as defense in depth.
# NOTE: a relative user_data_dir makes system Chrome fail to launch — always pass
# an absolute path (see open_context).
_ANTI_AUTOMATION_ARGS = ["--start-maximized", "--disable-blink-features=AutomationControlled"]
_MASK_WEBDRIVER = "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
_CHROME_CANDIDATES = [
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
]


def chrome_executable() -> str | None:
    """Path to the installed Chrome, or None if not found.

    Used directly by manual_login (a subprocess needs an exe path). open_context
    resolves Chrome independently via Playwright's channel="chrome"; this function
    only gates that on/off. The two paths could in principle disagree if Chrome is
    installed somewhere off the candidate list — unlikely for a standard install.
    """
    for path in _CHROME_CANDIDATES:
        if str(path) and path.exists():
            return str(path)
    return None


def _launch_chrome(client: str, platform: str, url: str, root: Path,
                   extra_args: list[str] = ()):
    """Popen the user's installed Chrome on the profile dir, opening `url`.

    Shared by manual_login (plain Chrome) and launch_debug_chrome (adds a
    remote-debugging port via extra_args). Always passes an ABSOLUTE user_data_dir
    (a relative one makes system Chrome fail to launch). Raises if Chrome isn't
    installed.
    """
    exe = chrome_executable()
    if not exe:
        raise RuntimeError("Chrome not found — install Chrome to log in to this platform.")
    pdir = profile_dir(client, platform, root)
    pdir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen([exe, *extra_args, f"--user-data-dir={pdir.resolve()}", url])


def manual_login(client: str, platform: str, url: str, root: Path = PROFILES_ROOT):
    """Launch the user's Chrome by hand (NO CDP/automation) on the profile dir.

    Habr's login captcha (Yandex SmartCaptcha) renders a blank box in any
    CDP-driven browser, so a normal manual login must use a plain Chrome process.
    Returns the Popen so the caller can terminate it after login. Raises if Chrome
    isn't installed.
    """
    return _launch_chrome(client, platform, url, root)


def cdp_endpoint(port: int) -> str:
    """CDP HTTP endpoint that Playwright's connect_over_cdp attaches to."""
    return f"http://localhost:{port}"


def launch_debug_chrome(client: str, platform: str, url: str, port: int,
                        root: Path = PROFILES_ROOT):
    """Launch the user's real Chrome on the profile with a remote-debugging port and
    NO automation flags. Yandex anti-bot rejects CDP-automation-launched Chrome but
    accepts this; Playwright then connect_over_cdp's to it. Returns the Popen — the
    caller MUST keep it alive for the whole layout run (closing drops the session)."""
    return _launch_chrome(client, platform, url, root,
                          extra_args=[f"--remote-debugging-port={port}"])


def profile_dir(client: str, platform: str, root: Path = PROFILES_ROOT) -> Path:
    return Path(root) / client / platform


def list_clients(root: Path = PROFILES_ROOT) -> list[str]:
    root = Path(root)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def list_accounts(client: str, root: Path = PROFILES_ROOT) -> list[str]:
    client_dir = Path(root) / client
    if not client_dir.exists():
        return []
    return sorted(p.name for p in client_dir.iterdir() if p.is_dir())


def _meta_path(client: str, platform: str, root: Path = PROFILES_ROOT) -> Path:
    return profile_dir(client, platform, root) / "meta.json"


def read_meta(client: str, platform: str, root: Path = PROFILES_ROOT) -> dict:
    path = _meta_path(client, platform, root)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_meta(client: str, platform: str, updates: dict, root: Path = PROFILES_ROOT) -> dict:
    """Merge `updates` into the profile's meta.json (creating the dir) and return it."""
    pdir = profile_dir(client, platform, root)
    pdir.mkdir(parents=True, exist_ok=True)
    meta = read_meta(client, platform, root)
    meta.update(updates)
    (pdir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


PLATFORMS = {
    "vc": {
        "build_document": vc_adapter.build_document,
        "editor_url": vc_adapter.EDITOR_URL,
        # The title field only renders inside the editor when logged in.
        "alive_marker": vc_adapter.TITLE_SEL,
    },
    "pikabu": {
        "build_document": pikabu_adapter.build_document,
        "editor_url": pikabu_adapter.ADD_URL,
        # The Tiptap editor body only mounts for a logged-in user.
        "alive_marker": pikabu_adapter.BODY_SEL,
    },
    "habr": {
        "build_document": habr_adapter.build_document,
        # is_alive navigates here and waits for ALIVE_SEL (the navbar pencil,
        # present only when logged in).
        "editor_url": habr_adapter.HOME_URL,
        "alive_marker": habr_adapter.ALIVE_SEL,
        # Login must use a non-CDP Chrome (captcha), so cmd_login launches Chrome
        # by hand at this URL instead of the Playwright flow.
        "manual_login": True,
        "login_url": habr_adapter.LOGIN_URL,
    },
    "smartlab": {
        "build_document": smartlab_adapter.build_document,
        # is_alive navigates here and waits for ALIVE_SEL (a logged-in-only
        # element). Editor form only renders for an authenticated user.
        "editor_url": smartlab_adapter.ADD_URL,
        "alive_marker": smartlab_adapter.ALIVE_SEL,
    },
    "dzen": {
        "build_document": dzen_adapter.build_document,
        "editor_url": dzen_adapter.STUDIO_URL,
        "alive_marker": dzen_adapter.ALIVE_SEL,
        # Dzen attaches to a live Chrome over CDP (see adapter docstring); it does
        # NOT use open_context. cli.py branches on this flag.
        "cdp_attach": True,
        "debug_port": dzen_adapter.DEBUG_PORT,
        "manual_login": True,
        "login_url": dzen_adapter.STUDIO_URL,
    },
}


def known_platforms() -> list[str]:
    return sorted(PLATFORMS)


def open_context(p, client: str, platform: str, headless: bool, root: Path = PROFILES_ROOT):
    """Launch a persistent context on this profile and return (ctx, page).

    Drives the installed Chrome (channel="chrome") with an ABSOLUTE user_data_dir,
    the automation switch removed and navigator.webdriver masked. Falls back to
    bundled Chromium only if Chrome isn't installed.
    """
    pdir = profile_dir(client, platform, root)
    pdir.mkdir(parents=True, exist_ok=True)
    kwargs = dict(
        user_data_dir=str(pdir.resolve()),
        headless=headless,
        args=_ANTI_AUTOMATION_ARGS,
        no_viewport=True,
        ignore_default_args=["--enable-automation"],
    )
    if chrome_executable():
        kwargs["channel"] = "chrome"
    ctx = p.chromium.launch_persistent_context(**kwargs)
    ctx.add_init_script(_MASK_WEBDRIVER)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return ctx, page


def is_alive(client: str, platform: str, headless: bool = True,
             timeout_ms: int = 8000, root: Path = PROFILES_ROOT) -> bool:
    """Probe the live site: open the editor and look for the logged-in marker.

    No cache — cookies can expire server-side at any time, so we always check.
    A missing profile folder counts as dead (needs login).
    """
    from playwright.sync_api import sync_playwright

    if not profile_dir(client, platform, root).exists():
        return False
    entry = PLATFORMS[platform]
    with sync_playwright() as p:
        ctx, page = open_context(p, client, platform, headless=headless, root=root)
        try:
            page.goto(entry["editor_url"], wait_until="domcontentloaded")
            page.wait_for_selector(entry["alive_marker"], timeout=timeout_ms)
            return True
        except Exception:
            return False
        finally:
            ctx.close()

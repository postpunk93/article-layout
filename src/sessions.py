# src/sessions.py
"""Single owner of browser-profile logic for the article-layout adapters.

A profile is a persistent Chromium context stored at
`.profiles/<client>/<platform>/`. The folder existing IS the fact that the
account is set up — there is no central registry. Per-profile metadata lives
in a `meta.json` beside the context. Liveness is never cached: `alive_on_page`
checks a logged-in marker on an already-open page every time.
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


def _login_argv(exe: str, pdir: Path, urls: list[str]) -> list[str]:
    return [exe, f"--user-data-dir={pdir.resolve()}", *urls]


def manual_login(client: str, urls: list[str], root: Path = PROFILES_ROOT):
    """Launch the user's plain Chrome (NO CDP) on the CLIENT's shared profile.

    Opens a tab per URL so the user can log into every platform in one sitting.
    Habr/Dzen SmartCaptcha renders blank under CDP, so login must use a plain Chrome
    process; afterwards layout/status reuse the profile via open_context. Returns the
    Popen so the caller can terminate it after login. Raises if Chrome isn't installed.
    """
    exe = chrome_executable()
    if not exe:
        raise RuntimeError("Chrome not found — install Chrome to log in.")
    pdir = profile_dir(client, root)
    pdir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(_login_argv(exe, pdir, urls))


def profile_dir(client: str, root: Path = PROFILES_ROOT) -> Path:
    return Path(root) / client


def list_clients(root: Path = PROFILES_ROOT) -> list[str]:
    root = Path(root)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def _meta_path(client: str, root: Path = PROFILES_ROOT) -> Path:
    return profile_dir(client, root) / "meta.json"


def read_meta(client: str, root: Path = PROFILES_ROOT) -> dict:
    path = _meta_path(client, root)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_meta(client: str, updates: dict, root: Path = PROFILES_ROOT) -> dict:
    """Merge `updates` into the client's meta.json (creating the dir) and return it."""
    pdir = profile_dir(client, root)
    pdir.mkdir(parents=True, exist_ok=True)
    meta = read_meta(client, root)
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
        # is_alive navigates here and waits for ALIVE_SEL (the studio "+", present only
        # when logged in). Editor opens from the studio for an authenticated user.
        "editor_url": dzen_adapter.STUDIO_URL,
        "alive_marker": dzen_adapter.ALIVE_SEL,
        # Login needs a non-CDP Chrome (Yandex SmartCaptcha), like Habr; afterwards
        # layout/is_alive reuse the profile via the standard open_context.
        "manual_login": True,
        "login_url": dzen_adapter.STUDIO_URL,
    },
}


def known_platforms() -> list[str]:
    return sorted(PLATFORMS)


def open_context(p, client: str, headless: bool, root: Path = PROFILES_ROOT):
    """Launch a persistent context on the CLIENT's shared profile; return (ctx, page).

    Drives installed Chrome (channel="chrome") on an ABSOLUTE user_data_dir, the
    automation switch removed and navigator.webdriver masked. Falls back to bundled
    Chromium only if Chrome isn't installed. The profile is shared by every platform —
    different domains, so logins don't collide.
    """
    pdir = profile_dir(client, root)
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


def alive_on_page(page, marker: str, timeout_ms: int = 8000) -> bool:
    """True if the logged-in marker appears on an already-navigated page."""
    try:
        page.wait_for_selector(marker, timeout=timeout_ms)
        return True
    except Exception:  # noqa: BLE001 — any failure means not logged in / not loaded
        return False

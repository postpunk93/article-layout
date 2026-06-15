# src/sessions.py
"""Single owner of browser-profile logic for the article-layout adapters.

A profile is a persistent Chromium context stored at `.profiles/<client>/` —
ONE shared profile per client, logged into every platform at once (the platforms
are different domains, so their logins don't collide). The folder existing IS the
fact that the client is set up — there is no central registry. Per-client metadata
lives in a `meta.json` beside the context. Liveness is never cached: it is
re-checked against the live site every time (see `orchestrator.check_alive`).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from src.adapters import vc, pikabu, habr, smartlab, dzen, lj, dtf, wp

PROFILES_ROOT = Path(".profiles")

# All adapters drive the user's INSTALLED Chrome (channel="chrome"), not bundled
# Chromium: Habr's login is recognized only by the real Chrome reading its own
# profile (bundled Chromium can't decrypt Chrome's app-bound cookies). The
# automation switch is removed and navigator.webdriver masked as defense in depth.
# NOTE: a relative user_data_dir makes system Chrome fail to launch — always pass
# an absolute path (see open_context).
_ANTI_AUTOMATION_ARGS = ["--start-maximized", "--disable-blink-features=AutomationControlled"]
_MASK_WEBDRIVER = "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"


def _ignore_default_args() -> list[str]:
    """Playwright default-args to suppress when launching the automated Chrome.

    Always drops --enable-automation (anti-bot hygiene). On macOS ALSO drops
    --use-mock-keychain: Playwright passes it by default, which makes Chrome use a
    fake Keychain — so it can neither decrypt the auth cookies that manual_login's
    real Chrome wrote with the OS Keychain key NOR keep them (it deletes the
    "corrupt" cookies on startup). Dropping it lets the automated Chrome share the
    real 'Chrome Safe Storage' Keychain key, so a saved login finally reads back.
    NOT changed on Windows: there Chrome uses DPAPI, the flag is a no-op, and the
    existing setup already works. See the cookie-decryption bug notes.
    """
    drop = ["--enable-automation"]
    if sys.platform == "darwin":
        drop.append("--use-mock-keychain")
    return drop
def _chrome_candidates() -> list[Path]:
    """Likely paths to the installed Chrome for the current OS.

    Only gates "is Chrome installed" — open_context resolves Chrome itself via
    Playwright channel="chrome". Keep ALL OS knowledge here; adapters stay OS-blind.
    """
    if sys.platform == "darwin":
        return [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    if sys.platform.startswith("win"):
        return [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
    return [Path("/usr/bin/google-chrome"), Path("/usr/bin/google-chrome-stable")]


def chrome_executable() -> str | None:
    """Path to the installed Chrome, or None if not found.

    Used directly by manual_login (a subprocess needs an exe path). open_context
    resolves Chrome independently via Playwright's channel="chrome"; this function
    only gates that on/off. The two paths could in principle disagree if Chrome is
    installed somewhere off the candidate list — unlikely for a standard install.
    """
    for path in _chrome_candidates():
        if str(path) and path.exists():
            return str(path)
    return None


def _login_argv(exe: str, pdir: Path, urls: list[str]) -> list[str]:
    """Chrome argv: exe, absolute shared-profile dir, then one tab per URL.

    This is a plain (non-Playwright) Chrome, so it already uses the real macOS
    Keychain to encrypt cookies — the automated Chrome is the side that must be
    told to match it (see _ignore_default_args).
    """
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
        "build_document": vc.build_document,
        "editor_url": vc.EDITOR_URL,
        # The title field only renders inside the editor when logged in.
        "alive_marker": vc.TITLE_SEL,
    },
    "dtf": {
        "build_document": dtf.build_document,
        "editor_url": dtf.EDITOR_URL,
        # Same Osnova editor as VC; the title field renders only when logged in.
        "alive_marker": dtf.TITLE_SEL,
    },
    "pikabu": {
        "build_document": pikabu.build_document,
        "editor_url": pikabu.ADD_URL,
        # The Tiptap editor body only mounts for a logged-in user.
        "alive_marker": pikabu.BODY_SEL,
    },
    "habr": {
        "build_document": habr.build_document,
        # Liveness navigates to the new-article editor and waits for the editor body
        # (ALIVE_SEL = BODY_SEL), which mounts only for a logged-in user.
        "editor_url": habr.NEW_ARTICLE_URL,
        "alive_marker": habr.ALIVE_SEL,
        "manual_login": True,
        "login_url": habr.LOGIN_URL,
    },
    "smartlab": {
        "build_document": smartlab.build_document,
        # Liveness navigates here and waits for ALIVE_SEL (a logged-in-only
        # element). Editor form only renders for an authenticated user.
        "editor_url": smartlab.ADD_URL,
        "alive_marker": smartlab.ALIVE_SEL,
    },
    "dzen": {
        "build_document": dzen.build_document,
        # Liveness navigates here and waits for ALIVE_SEL (the studio "+", present only
        # when logged in). Editor opens from the studio for an authenticated user.
        "editor_url": dzen.STUDIO_URL,
        "alive_marker": dzen.ALIVE_SEL,
        # Login needs a non-CDP Chrome (Yandex SmartCaptcha), like Habr; afterwards
        # layout/status reuse the profile via the standard open_context.
        "manual_login": True,
        "login_url": dzen.STUDIO_URL,
    },
    "lj": {
        "build_document": lj.build_document,
        # Liveness navigates here and waits for ALIVE_SEL (the Draft.js body, present
        # only when logged in). Standard open_context login (like VC/Smartlab) — the
        # default profile drives fine under CDP, no manual_login needed.
        "editor_url": lj.POST_URL,
        "alive_marker": lj.ALIVE_SEL,
    },
    "ruminlab": {
        "build_document": wp.build_document,
        # Liveness navigates here and waits for ALIVE_SEL (the editor inserter toggle,
        # a top-window element present only when the Gutenberg editor loads = logged in).
        "editor_url": wp.EDITOR_URL,
        "alive_marker": wp.ALIVE_SEL,
        # Plain WordPress login/password — standard open_context (like VC/LJ), no captcha.
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
        ignore_default_args=_ignore_default_args(),
    )
    if chrome_executable():
        kwargs["channel"] = "chrome"
    ctx = p.chromium.launch_persistent_context(**kwargs)
    ctx.add_init_script(_MASK_WEBDRIVER)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return ctx, page

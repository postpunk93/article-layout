# src/sessions.py
"""Single owner of browser-profile logic for the article-layout adapters.

A profile is a persistent Chromium context stored at
`.profiles/<client>/<platform>/`. The folder existing IS the fact that the
account is set up — there is no central registry. Per-profile metadata lives
in a `meta.json` beside the context. Liveness is never cached: `is_alive`
probes the live site every time.
"""
from pathlib import Path

PROFILES_ROOT = Path(".profiles")


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

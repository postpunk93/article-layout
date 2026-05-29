# src/sessions.py
"""Single owner of browser-profile logic for the article-layout adapters.

A profile is a persistent Chromium context stored at
`.profiles/<client>/<platform>/`. The folder existing IS the fact that the
account is set up — there is no central registry. Per-profile metadata lives
in a `meta.json` beside the context. Liveness is never cached: `is_alive`
probes the live site every time.
"""
import json
from pathlib import Path

from src import vc_adapter, pikabu_adapter

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
}


def known_platforms() -> list[str]:
    return sorted(PLATFORMS)

# tests/test_sessions_registry.py
from src import sessions


def test_registry_has_vc_and_pikabu():
    assert set(sessions.PLATFORMS) == {"vc", "pikabu"}


def test_each_platform_entry_is_complete():
    for key, entry in sessions.PLATFORMS.items():
        assert callable(entry["build_document"]), key
        assert entry["editor_url"].startswith("http"), key
        assert entry["alive_marker"], key


def test_known_platforms_helper():
    assert sessions.known_platforms() == ["pikabu", "vc"]

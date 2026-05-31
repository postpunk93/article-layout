# tests/test_sessions_registry.py
from src import sessions


def test_registry_has_all_platforms():
    assert set(sessions.PLATFORMS) == {"vc", "pikabu", "habr", "smartlab", "dzen"}


def test_each_platform_entry_is_complete():
    for key, entry in sessions.PLATFORMS.items():
        assert callable(entry["build_document"]), key
        assert entry["editor_url"].startswith("http"), key
        assert entry["alive_marker"], key


def test_known_platforms_helper():
    assert sessions.known_platforms() == ["dzen", "habr", "pikabu", "smartlab", "vc"]


def test_habr_registered_with_contract():
    entry = sessions.PLATFORMS["habr"]
    assert callable(entry["build_document"])
    assert entry["editor_url"].startswith("http")
    assert entry["alive_marker"]
    assert "habr" in sessions.known_platforms()


def test_smartlab_registered_with_contract():
    entry = sessions.PLATFORMS["smartlab"]
    assert callable(entry["build_document"])
    assert entry["editor_url"].startswith("http")
    assert entry["alive_marker"]
    assert "smartlab" in sessions.known_platforms()


def test_dzen_registered_with_contract():
    entry = sessions.PLATFORMS["dzen"]
    assert callable(entry["build_document"])
    assert entry["editor_url"].startswith("http")
    assert entry["alive_marker"]
    assert entry["cdp_attach"] is True
    assert "dzen" in sessions.known_platforms()

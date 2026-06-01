# tests/test_sessions_registry.py
from src import sessions


def test_registry_has_all_platforms():
    assert set(sessions.PLATFORMS) == {"vc", "pikabu", "habr", "smartlab", "dzen", "lj", "dtf"}


def test_each_platform_entry_is_complete():
    for key, entry in sessions.PLATFORMS.items():
        assert callable(entry["build_document"]), key
        assert entry["editor_url"].startswith("http"), key
        assert entry["alive_marker"], key


def test_known_platforms_helper():
    assert sessions.known_platforms() == ["dtf", "dzen", "habr", "lj", "pikabu", "smartlab", "vc"]


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
    # Dzen logs in like Habr (non-CDP Chrome for the Yandex captcha), then reuses
    # the profile via open_context — no cdp_attach special-casing.
    assert entry["manual_login"] is True
    assert "cdp_attach" not in entry
    assert "dzen" in sessions.known_platforms()


def test_lj_registered_with_contract():
    entry = sessions.PLATFORMS["lj"]
    assert callable(entry["build_document"])
    assert entry["editor_url"].startswith("http")
    assert entry["alive_marker"]
    # Standard CDP login (like VC/Smartlab) — no manual_login unless a captcha appears.
    assert "manual_login" not in entry
    assert "lj" in sessions.known_platforms()


def test_dtf_registered_with_contract():
    entry = sessions.PLATFORMS["dtf"]
    assert callable(entry["build_document"])
    assert entry["editor_url"].startswith("http")
    assert entry["alive_marker"]
    # Same Osnova engine as VC; standard CDP login, no manual_login.
    assert "manual_login" not in entry
    assert "dtf" in sessions.known_platforms()

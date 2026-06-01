# tests/test_sessions_meta.py
from src import sessions


def test_read_meta_missing_returns_empty_dict(tmp_path):
    assert sessions.read_meta("acme", root=tmp_path) == {}


def test_write_then_read_meta_round_trip(tmp_path):
    sessions.write_meta("acme", {"label": "ACME", "login": "a@b.c"}, root=tmp_path)
    assert sessions.read_meta("acme", root=tmp_path) == {"label": "ACME", "login": "a@b.c"}


def test_write_meta_creates_profile_dir(tmp_path):
    sessions.write_meta("new", {"label": "x"}, root=tmp_path)
    assert (tmp_path / "new" / "meta.json").is_file()


def test_write_meta_merges_with_existing(tmp_path):
    sessions.write_meta("acme", {"label": "ACME"}, root=tmp_path)
    sessions.write_meta("acme", {"last_login_at": "2026-05-29"}, root=tmp_path)
    assert sessions.read_meta("acme", root=tmp_path) == {"label": "ACME", "last_login_at": "2026-05-29"}

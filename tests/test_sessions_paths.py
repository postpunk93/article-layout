# tests/test_sessions_paths.py
from pathlib import Path

from src import sessions


def test_profile_dir_builds_client_path():
    root = Path("/tmp/profiles")
    assert sessions.profile_dir("acme", root=root) == root / "acme"


def test_list_clients_reads_folder_names(tmp_path):
    (tmp_path / "acme").mkdir()
    (tmp_path / "beta").mkdir()
    assert sessions.list_clients(root=tmp_path) == ["acme", "beta"]


def test_list_clients_empty_when_root_missing(tmp_path):
    assert sessions.list_clients(root=tmp_path / "nope") == []

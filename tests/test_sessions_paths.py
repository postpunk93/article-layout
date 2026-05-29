# tests/test_sessions_paths.py
from pathlib import Path

from src import sessions


def test_profile_dir_builds_client_platform_path():
    root = Path("/tmp/profiles")
    assert sessions.profile_dir("acme", "vc", root=root) == root / "acme" / "vc"


def test_list_clients_reads_folder_names(tmp_path):
    (tmp_path / "acme" / "vc").mkdir(parents=True)
    (tmp_path / "beta" / "pikabu").mkdir(parents=True)
    assert sessions.list_clients(root=tmp_path) == ["acme", "beta"]


def test_list_clients_empty_when_root_missing(tmp_path):
    assert sessions.list_clients(root=tmp_path / "nope") == []


def test_list_accounts_reads_platform_folders(tmp_path):
    (tmp_path / "acme" / "vc").mkdir(parents=True)
    (tmp_path / "acme" / "pikabu").mkdir(parents=True)
    assert sessions.list_accounts("acme", root=tmp_path) == ["pikabu", "vc"]


def test_list_accounts_empty_for_unknown_client(tmp_path):
    assert sessions.list_accounts("ghost", root=tmp_path) == []

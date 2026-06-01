from pathlib import Path
from src import sessions


def test_login_argv_has_profile_and_all_urls():
    argv = sessions._login_argv("C:/chrome.exe", Path("/p/acme"), ["https://a", "https://b"])
    assert argv[0] == "C:/chrome.exe"
    assert any(a.startswith("--user-data-dir=") and a.endswith("acme") for a in argv)
    assert argv[-2:] == ["https://a", "https://b"]


def test_login_argv_tolerates_no_urls():
    argv = sessions._login_argv("C:/chrome.exe", Path("/p/acme"), [])
    assert argv[0] == "C:/chrome.exe"
    assert len(argv) == 2  # exe + user-data-dir only

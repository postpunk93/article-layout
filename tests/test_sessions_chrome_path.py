from pathlib import Path
from src import sessions


def test_mac_candidates_include_app_bundle(monkeypatch):
    monkeypatch.setattr(sessions.sys, "platform", "darwin")
    cands = sessions._chrome_candidates()
    assert any("Google Chrome.app" in str(p) for p in cands)


def test_win_candidates_include_chrome_exe(monkeypatch):
    monkeypatch.setattr(sessions.sys, "platform", "win32")
    cands = sessions._chrome_candidates()
    assert any(str(p).lower().endswith("chrome.exe") for p in cands)


def test_chrome_executable_returns_existing(monkeypatch, tmp_path):
    fake = tmp_path / "chrome"
    fake.write_text("")
    monkeypatch.setattr(sessions, "_chrome_candidates", lambda: [tmp_path / "nope", fake])
    assert sessions.chrome_executable() == str(fake)


def test_chrome_executable_none_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(sessions, "_chrome_candidates", lambda: [tmp_path / "nope"])
    assert sessions.chrome_executable() is None

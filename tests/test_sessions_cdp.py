# tests/test_sessions_cdp.py
from src import sessions


def test_cdp_endpoint_url():
    assert sessions.cdp_endpoint(9222) == "http://localhost:9222"

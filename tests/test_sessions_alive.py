from src import sessions


class _Page:
    def __init__(self, ok):
        self.ok = ok
        self.waited = None

    def wait_for_selector(self, marker, timeout):
        self.waited = (marker, timeout)
        if not self.ok:
            raise RuntimeError("not found")


def test_alive_on_page_true_when_marker_found():
    p = _Page(ok=True)
    assert sessions.alive_on_page(p, ".x", timeout_ms=1234) is True
    assert p.waited == (".x", 1234)


def test_alive_on_page_false_when_marker_missing():
    assert sessions.alive_on_page(_Page(ok=False), ".x") is False

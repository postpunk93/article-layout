# tests/test_orchestrator.py
import pytest

from src import orchestrator


def test_parse_platforms_explicit_list():
    assert orchestrator.parse_platforms("vc,pikabu", ["pikabu", "vc"]) == ["vc", "pikabu"]


def test_parse_platforms_all_expands_to_known():
    assert orchestrator.parse_platforms("all", ["pikabu", "vc"]) == ["pikabu", "vc"]


def test_parse_platforms_dedupes_preserving_order():
    assert orchestrator.parse_platforms("vc,pikabu,vc", ["pikabu", "vc"]) == ["vc", "pikabu"]


def test_parse_platforms_rejects_unknown():
    with pytest.raises(ValueError) as e:
        orchestrator.parse_platforms("vc,telegram", ["pikabu", "vc"])
    assert "telegram" in str(e.value)


class _MarkerPage:
    def __init__(self, found):
        self.found = found

    def wait_for_selector(self, marker, timeout):
        if not self.found:
            raise RuntimeError("missing")


def test_check_alive_empty_when_all_found():
    pages = {"vc": _MarkerPage(True), "pikabu": _MarkerPage(True)}
    markers = {"vc": ".v", "pikabu": ".p"}
    assert orchestrator.check_alive(pages, markers, timeout_ms=10) == []


def test_check_alive_lists_dead_platforms_in_order():
    pages = {"vc": _MarkerPage(True), "pikabu": _MarkerPage(False)}
    markers = {"vc": ".v", "pikabu": ".p"}
    assert orchestrator.check_alive(pages, markers, timeout_ms=10) == ["pikabu"]


class _FakePage:
    def __init__(self, closed):
        self.closed = closed

    def is_closed(self):
        return self.closed


class _FakeCtx:
    def __init__(self, pages):
        self.pages = pages


def test_wait_returns_immediately_when_all_closed():
    ctx = _FakeCtx([_FakePage(closed=True)])
    pumped = []
    orchestrator.wait_until_all_closed([("vc", ctx)], pump=lambda pg: pumped.append(pg))
    assert pumped == []  # nothing live, so never pumped


def test_wait_blocks_until_user_closes_window():
    page = _FakePage(closed=False)
    ctx = _FakeCtx([page])
    calls = {"n": 0}

    def pump(_pg):
        calls["n"] += 1
        page.closed = True  # user closes the window during the wait

    orchestrator.wait_until_all_closed([("vc", ctx)], pump=pump)
    assert calls["n"] == 1


def test_wait_survives_pump_exception():
    page = _FakePage(closed=False)
    ctx = _FakeCtx([page])
    state = {"first": True}

    def pump(_pg):
        if state["first"]:
            state["first"] = False
            page.closed = True
            raise RuntimeError("target closed")  # window vanished mid-pump

    orchestrator.wait_until_all_closed([("vc", ctx)], pump=pump)  # must return, not raise


def test_wait_treats_errored_context_as_closed():
    class _Boom:
        @property
        def pages(self):
            raise RuntimeError("target closed")

    orchestrator.wait_until_all_closed([("vc", _Boom())], pump=lambda pg: None)


def test_wait_returns_only_after_every_window_closed():
    page_a = _FakePage(closed=False)
    page_b = _FakePage(closed=False)
    ctx_a = _FakeCtx([page_a])
    ctx_b = _FakeCtx([page_b])
    pumps = {"n": 0}

    def pump(_pg):
        pumps["n"] += 1
        if pumps["n"] == 1:
            page_a.closed = True   # first window closed; one still open -> must keep waiting
        elif pumps["n"] == 2:
            page_b.closed = True   # now all closed -> next check returns

    orchestrator.wait_until_all_closed([("vc", ctx_a), ("pikabu", ctx_b)], pump=pump)
    assert pumps["n"] == 2  # proves it did NOT return after only the first window closed

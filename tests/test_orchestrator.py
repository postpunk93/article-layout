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


def test_precheck_all_alive_is_ok():
    alive = lambda c, p: True
    ok, dead = orchestrator.precheck("acme", ["vc", "pikabu"], alive)
    assert ok is True
    assert dead == []


def test_precheck_one_dead_blocks_everything():
    alive = lambda c, p: p != "pikabu"
    ok, dead = orchestrator.precheck("acme", ["vc", "pikabu"], alive)
    assert ok is False
    assert dead == [("acme", "pikabu")]

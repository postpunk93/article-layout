# tests/test_parser_runs.py
from bs4 import BeautifulSoup
from src.parser import spans_to_runs

ITALIC = {"c3", "c5", "c8"}
BOLD = {"c1", "c9", "c10"}


def _p(html):
    return BeautifulSoup(html, "html.parser").find("p")


def test_merges_adjacent_same_style_spans():
    p = _p('<p><span class="c0">Hello </span><span class="c0">world</span></p>')
    runs = spans_to_runs(p, ITALIC, BOLD)
    assert len(runs) == 1
    assert runs[0].text == "Hello world"
    assert runs[0].bold is False and runs[0].italic is False


def test_distinguishes_italic_run():
    p = _p('<p><span class="c0">plain </span><span class="c8">italic</span></p>')
    runs = spans_to_runs(p, ITALIC, BOLD)
    assert len(runs) == 2
    assert runs[1].italic is True


def test_classless_span_is_normal_and_entities_decoded():
    p = _p('<p><span>caf&eacute;</span></p>')
    runs = spans_to_runs(p, ITALIC, BOLD)
    assert runs[0].text == "café"
    assert runs[0].bold is False and runs[0].italic is False

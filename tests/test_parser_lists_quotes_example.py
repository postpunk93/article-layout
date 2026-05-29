from pathlib import Path

from src.parser import parse
from src.ir import ListBlock, Quote

doc = parse(Path("tests/fixtures/lists-quotes/index.html").read_text(encoding="utf-8"))
LISTS = [b for b in doc.blocks if isinstance(b, ListBlock)]
QUOTES = [b for b in doc.blocks if isinstance(b, Quote)]


def test_two_lists_one_unordered_one_ordered():
    assert len(LISTS) == 2
    assert LISTS[0].ordered is False          # <ul> appears first in the doc
    assert LISTS[1].ordered is True           # <ol> second


def test_unordered_list_has_three_items_starting_zara():
    ul = LISTS[0]
    assert len(ul.items) == 3
    assert ul.items[0].runs[0].text.strip() == "Zara,"


def test_ordered_list_has_four_items():
    assert len(LISTS[1].items) == 4
    assert "".join(r.text for r in LISTS[1].items[0].runs).strip() == "Сотрудник приезжал,"


def test_one_quote_present_and_nonempty():
    assert len(QUOTES) == 1
    text = "".join(r.text for r in QUOTES[0].runs).strip()
    assert len(text) > 0
    assert text.startswith("Прежде чем вкладываться, мы проверили")


def test_no_empty_list_items():
    for lb in LISTS:
        assert all("".join(r.text for r in it.runs).strip() for it in lb.items)

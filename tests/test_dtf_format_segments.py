from src.ir import Run
from src.dtf_adapter import format_segments


def test_no_formatting_returns_empty():
    assert format_segments([Run("plain text", False, False)]) == []


def test_bold_run_offsets():
    runs = [Run("a ", False, False), Run("bold", True, False), Run(" end", False, False)]
    assert format_segments(runs) == [(2, 6, True, False)]


def test_italic_and_bolditalic():
    runs = [Run("x", False, True), Run("y", True, True)]
    assert format_segments(runs) == [(0, 1, False, True), (1, 2, True, True)]

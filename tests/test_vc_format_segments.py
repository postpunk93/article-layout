from src.ir import Run
from src.adapters.vc import format_segments


def test_no_formatting_returns_empty():
    runs = [Run("plain text", False, False)]
    assert format_segments(runs) == []


def test_bold_run_offsets():
    # "a " (0-2) then "bold" (2-6) bold then " end" (6-10)
    runs = [Run("a ", False, False), Run("bold", True, False), Run(" end", False, False)]
    assert format_segments(runs) == [(2, 6, True, False)]


def test_italic_and_bolditalic():
    runs = [Run("x", False, True), Run("y", True, True)]
    # "x" italic at 0-1; "y" bold+italic at 1-2
    assert format_segments(runs) == [(0, 1, False, True), (1, 2, True, True)]


def test_empty_run_skipped_but_advances_nothing():
    runs = [Run("", True, False), Run("hi", True, False)]
    assert format_segments(runs) == [(0, 2, True, False)]

# tests/test_parser_styles.py
from src.parser import style_class_sets

STYLE = (
    '.c0{color:#000;font-weight:400;font-style:normal}'
    '.c1{font-weight:700;font-style:normal}'
    '.c3{font-weight:400;font-style:italic}'
    '.c8{font-style:italic}'
    '.c10{font-size:23pt;font-weight:700}'
)


def test_style_class_sets_finds_italic_and_bold():
    italic, bold = style_class_sets(f'<style>{STYLE}</style>')
    assert italic == {"c3", "c8"}
    assert bold == {"c1", "c10"}


# append to tests/test_parser_styles.py
from pathlib import Path

EXAMPLE = Path("example/170/index.html").read_text(encoding="utf-8")


def test_style_class_sets_on_real_example():
    italic, bold = style_class_sets(EXAMPLE)
    assert {"c3", "c5", "c8"}.issubset(italic)
    assert {"c1", "c9", "c10"}.issubset(bold)


def test_handles_tab_newline_whitespace_and_multiple_style_blocks():
    html = (
        "<style>.c1 {\n\tfont-weight:\t700;\n\tfont-style:\n italic\n}</style>"
        "<style>.c2{font-style:italic}</style>"
    )
    italic, bold = style_class_sets(html)
    assert italic == {"c1", "c2"}
    assert bold == {"c1"}

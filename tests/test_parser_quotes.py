from src.parser import parse, yellow_class_set
from src.ir import Quote, Paragraph

STYLE = (
    ".c0{font-weight:400;font-style:normal}"
    ".c10{background-color:#ffff00}"
    ".c13{background-color:#c9daf8}"
)


def test_yellow_class_set_finds_only_yellow():
    classes = yellow_class_set(f"<style>{STYLE}</style>")
    assert classes == {"c10"}


def test_fully_yellow_paragraph_is_quote():
    html = f"<html><head><style>{STYLE}</style></head><body>" \
           '<p class="c3"><span class="c0 c10">a real quote</span></p></body></html>'
    doc = parse(html)
    assert isinstance(doc.blocks[0], Quote)
    assert doc.blocks[0].runs[0].text == "a real quote"


def test_partial_yellow_paragraph_stays_paragraph():
    html = f"<html><head><style>{STYLE}</style></head><body>" \
           '<p class="c3"><span class="c0">plain </span>' \
           '<span class="c0 c10">highlit</span></p></body></html>'
    doc = parse(html)
    assert isinstance(doc.blocks[0], Paragraph)


def test_yellow_quote_with_inter_run_space_span_stays_quote():
    html = f"<html><head><style>{STYLE}</style></head><body>" \
           '<p class="c3"><span class="c0 c10">first</span>' \
           '<span class="c0"> </span>' \
           '<span class="c0 c10">second</span></p></body></html>'
    assert isinstance(parse(html).blocks[0], Quote)


def test_non_yellow_highlight_is_not_a_quote():
    html = f"<html><head><style>{STYLE}</style></head><body>" \
           '<p class="c3"><span class="c0 c13">blue</span></p></body></html>'
    doc = parse(html)
    assert isinstance(doc.blocks[0], Paragraph)

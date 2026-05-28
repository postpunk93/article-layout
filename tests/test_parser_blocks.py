# tests/test_parser_blocks.py
from src.parser import parse
from src.ir import Heading, Paragraph

HTML = """
<html><head><style>
.c0{font-weight:400;font-style:normal}
.c8{font-style:italic}
.c1{font-weight:700}
</style></head><body>
<h1 class="c6"><span class="c1">My </span><span class="c1">Title</span></h1>
<h2 class="c2"><span class="c1">Section One</span></h2>
<p class="c4"><span class="c0">Plain text </span><span class="c8">italic bit</span></p>
<p class="c4"><span></span></p>
</body></html>
"""


def test_first_h1_becomes_title():
    doc = parse(HTML)
    assert doc.title == "My Title"


def test_h2_becomes_heading_block():
    doc = parse(HTML)
    assert isinstance(doc.blocks[0], Heading)
    assert doc.blocks[0].level == 2
    assert doc.blocks[0].runs[0].text == "Section One"


def test_paragraph_runs_and_empty_dropped():
    doc = parse(HTML)
    assert isinstance(doc.blocks[1], Paragraph)
    assert doc.blocks[1].runs[0].text == "Plain text "
    assert doc.blocks[1].runs[1].italic is True
    # the empty <p> produced no block
    assert len(doc.blocks) == 2

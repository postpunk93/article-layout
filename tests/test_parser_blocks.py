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


TWO_H1 = """
<html><head><style>.c0{font-weight:400;font-style:normal}</style></head><body>
<h1 class="c6"><span class="c0">First Title</span></h1>
<p class="c4"><span class="c0">Body para</span></p>
<h1 class="c6"><span class="c0">Second Title</span></h1>
</body></html>
"""

NO_H1 = """
<html><head><style>.c0{font-weight:400;font-style:normal}</style></head><body>
<h2 class="c2"><span class="c0">Only a section</span></h2>
<p class="c4"><span class="c0">text</span></p>
</body></html>
"""

ORDERED = """
<html><head><style>.c0{font-weight:400;font-style:normal}</style></head><body>
<h1 class="c6"><span class="c0">T</span></h1>
<p class="c4"><span class="c0">one</span></p>
<h2 class="c2"><span class="c0">mid</span></h2>
<p class="c4"><span class="c0">two</span></p>
</body></html>
"""


def test_only_first_h1_is_title_second_h1_ignored():
    doc = parse(TWO_H1)
    assert doc.title == "First Title"
    # the second h1 must NOT overwrite the title and must NOT become a block
    texts = ["".join(r.text for r in b.runs) for b in doc.blocks]
    assert "Second Title" not in texts
    assert all(not (isinstance(b, Heading) and b.level == 1) for b in doc.blocks)


def test_document_with_no_h1_has_empty_title():
    doc = parse(NO_H1)
    assert doc.title == ""
    assert isinstance(doc.blocks[0], Heading)


def test_block_order_preserved_p_h2_p():
    doc = parse(ORDERED)
    kinds = [(type(b).__name__, "".join(r.text for r in b.runs)) for b in doc.blocks]
    assert kinds == [("Paragraph", "one"), ("Heading", "mid"), ("Paragraph", "two")]


H3_DOC = """
<html><head><style>.c0{font-weight:400;font-style:normal}</style></head><body>
<h1 class="c6"><span class="c0">Title</span></h1>
<h2 class="c2"><span class="c0">Section</span></h2>
<h3 class="c3"><span class="c0">Subsection</span></h3>
<p class="c4"><span class="c0">body</span></p>
</body></html>
"""

# chernika-style doc: H3 used with no H2 above it. Content must NOT be dropped.
H3_ONLY = """
<html><head><style>.c0{font-weight:400;font-style:normal}</style></head><body>
<h1 class="c6"><span class="c0">T</span></h1>
<h3 class="c3"><span class="c0">Lonely sub</span></h3>
<p class="c4"><span class="c0">body</span></p>
</body></html>
"""


def test_h3_becomes_heading_level_3():
    doc = parse(H3_DOC)
    h3 = doc.blocks[1]
    assert isinstance(h3, Heading)
    assert h3.level == 3
    assert h3.runs[0].text == "Subsection"


def test_h2_and_h3_levels_and_order_preserved():
    doc = parse(H3_DOC)
    kinds = [(type(b).__name__, getattr(b, "level", None)) for b in doc.blocks]
    assert kinds == [("Heading", 2), ("Heading", 3), ("Paragraph", None)]


def test_h3_without_h2_is_still_parsed():
    doc = parse(H3_ONLY)
    assert isinstance(doc.blocks[0], Heading)
    assert doc.blocks[0].level == 3
    assert doc.blocks[0].runs[0].text == "Lonely sub"

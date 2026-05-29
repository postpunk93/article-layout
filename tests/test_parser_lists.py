from src.parser import parse
from src.ir import ListBlock, Paragraph

HTML = """
<html><head><style>
.c0{font-weight:400;font-style:normal}
.c1{font-weight:700}
.c8{font-style:italic}
</style></head><body>
<p class="c4"><span class="c0">intro</span></p>
<ul class="c11"><li class="c2"><span class="c0">Zara, </span></li>
<li class="c2"><span class="c1">bold item</span></li></ul>
<ol class="c11" start="1"><li class="c2"><span class="c0">step one</span></li>
<li class="c2"><span class="c8">step two</span></li>
<li class="c2"><span class="c0">step three</span></li></ol>
<p class="c4"><span class="c0">outro</span></p>
</body></html>
"""


def test_unordered_list_parsed_with_items():
    doc = parse(HTML)
    lists = [b for b in doc.blocks if isinstance(b, ListBlock)]
    ul = lists[0]
    assert ul.ordered is False
    assert [i.runs[0].text.strip() for i in ul.items] == ["Zara,", "bold item"]


def test_ordered_list_parsed_with_three_items():
    doc = parse(HTML)
    ol = [b for b in doc.blocks if isinstance(b, ListBlock)][1]
    assert ol.ordered is True
    assert len(ol.items) == 3


def test_list_item_preserves_inline_formatting():
    doc = parse(HTML)
    ul = [b for b in doc.blocks if isinstance(b, ListBlock)][0]
    assert ul.items[1].runs[0].bold is True       # "bold item"
    ol = [b for b in doc.blocks if isinstance(b, ListBlock)][1]
    assert ol.items[1].runs[0].italic is True      # "step two"


def test_lists_keep_position_between_paragraphs():
    doc = parse(HTML)
    kinds = [type(b).__name__ for b in doc.blocks]
    assert kinds == ["Paragraph", "ListBlock", "ListBlock", "Paragraph"]


def test_empty_list_items_dropped():
    html = HTML.replace('<li class="c2"><span class="c0">step three</span></li>',
                        '<li class="c2"><span></span></li>')
    doc = parse(html)
    ol = [b for b in doc.blocks if isinstance(b, ListBlock)][1]
    assert len(ol.items) == 2

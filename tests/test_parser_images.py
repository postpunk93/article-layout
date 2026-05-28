# tests/test_parser_images.py
from src.parser import parse
from src.ir import Image, Paragraph

STYLE = """<style>
.c0{font-weight:400;font-style:normal}
.c3{font-style:italic}
</style>"""

# image followed by ITALIC trailing text in the same <p> -> caption
CAPTIONED = f"""<html><head>{STYLE}</head><body>
<p class="c4"><span><img src="images/image8.png"></span><span><br></span><span class="c3">Set sketch, take 2</span></p>
</body></html>"""

# image followed by NORMAL trailing text in the same <p> -> no caption + standalone paragraph
UNCAPTIONED = f"""<html><head>{STYLE}</head><body>
<p class="c4"><span><img src="images/image5.png"></span><span class="c0"><br>This is me)</span></p>
</body></html>"""

# image alone in its <p>
ALONE = f"""<html><head>{STYLE}</head><body>
<p class="c4"><span><img src="images/image9.png"></span></p>
<p class="c4"><span class="c0">Regular following paragraph.</span></p>
</body></html>"""


def test_italic_trailing_text_becomes_caption():
    doc = parse(CAPTIONED)
    assert isinstance(doc.blocks[0], Image)
    assert doc.blocks[0].file == "image8.png"
    assert doc.blocks[0].caption is not None
    assert doc.blocks[0].caption[0].text == "Set sketch, take 2"
    assert len(doc.blocks) == 1


def test_normal_trailing_text_is_standalone_paragraph():
    doc = parse(UNCAPTIONED)
    assert isinstance(doc.blocks[0], Image)
    assert doc.blocks[0].caption is None
    assert isinstance(doc.blocks[1], Paragraph)
    assert doc.blocks[1].runs[0].text.strip() == "This is me)"


def test_image_alone_then_normal_paragraph():
    doc = parse(ALONE)
    assert isinstance(doc.blocks[0], Image)
    assert doc.blocks[0].caption is None
    assert isinstance(doc.blocks[1], Paragraph)
    assert doc.blocks[1].runs[0].text == "Regular following paragraph."


def test_caption_preserves_inter_word_space_across_spans():
    # trailing italic text split across spans with a whitespace-only span between words
    html = (
        '<html><head><style>.c3{font-style:italic}</style></head><body>'
        '<p class="c4"><span><img src="images/imageX.png"></span>'
        '<span class="c3">word</span><span class="c3"> </span><span class="c3">two</span></p>'
        '</body></html>'
    )
    from src.parser import parse
    doc = parse(html)
    assert doc.blocks[0].caption is not None
    assert doc.blocks[0].caption[0].text == "word two"


def test_mixed_italic_and_normal_trailing_is_not_a_caption():
    html = (
        '<html><head><style>.c0{font-weight:400;font-style:normal}.c3{font-style:italic}</style></head><body>'
        '<p class="c4"><span><img src="images/imageX.png"></span>'
        '<span class="c3">italic </span><span class="c0">normal</span></p>'
        '</body></html>'
    )
    from src.parser import parse
    from src.ir import Image, Paragraph
    doc = parse(html)
    assert isinstance(doc.blocks[0], Image)
    assert doc.blocks[0].caption is None  # not ALL runs italic -> no caption
    assert isinstance(doc.blocks[1], Paragraph)


def test_bold_only_trailing_is_not_a_caption():
    html = (
        '<html><head><style>.c0{font-weight:400;font-style:normal}.c1{font-weight:700}</style></head><body>'
        '<p class="c4"><span><img src="images/imageX.png"></span>'
        '<span class="c1">bold heading-ish</span></p>'
        '</body></html>'
    )
    from src.parser import parse
    from src.ir import Image, Paragraph
    doc = parse(html)
    assert doc.blocks[0].caption is None  # bold != italic, so not a caption
    assert isinstance(doc.blocks[1], Paragraph)

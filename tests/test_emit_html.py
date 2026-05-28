# tests/test_emit_html.py
from src.ir import Document, Heading, Paragraph, Image, Run
from src.emit_html import emit_body


def test_emit_headings_paragraphs_formatting_and_markers():
    doc = Document(
        title="T",
        blocks=[
            Heading(level=2, runs=[Run("Sec", False, False)]),
            Paragraph(runs=[Run("a ", False, False), Run("bold", True, False), Run(" ", False, False), Run("it", False, True)]),
            Image(file="image5.png", caption=None),
            Image(file="image8.png", caption=[Run("cap", False, True)]),
        ],
    )
    html = emit_body(doc)
    assert "<h2>Sec</h2>" in html
    assert "<strong>bold</strong>" in html
    assert "<em>it</em>" in html
    assert "[[IMG:image5.png]]" in html
    assert "[[IMG:image8.png]]" in html


def test_html_special_chars_escaped():
    doc = Document(title="T", blocks=[Paragraph(runs=[Run("a < b & c", False, False)])])
    html = emit_body(doc)
    assert "a &lt; b &amp; c" in html

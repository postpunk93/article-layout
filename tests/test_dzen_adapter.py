# tests/test_dzen_adapter.py
from src.adapters import dzen
from src.ir import Document, Paragraph, Quote, Image, Run


def test_body_html_emits_real_blockquote_and_img_markers():
    doc = Document(title="T", blocks=[
        Paragraph(runs=[Run("hello")]),
        Quote(runs=[Run("quoted")]),
        Image(file="image1.png", caption=[Run("cap")]),
    ])
    html = dzen.body_html(doc)
    assert "<blockquote>quoted</blockquote>" in html
    assert "[[IMG:image1.png]]" in html
    assert "data:image" not in html
    assert "[[CAP:" not in html

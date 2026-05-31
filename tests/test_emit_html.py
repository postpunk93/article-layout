# tests/test_emit_html.py
from src.ir import Document, Heading, Paragraph, Image, ListBlock, ListItem, Quote, Run
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


def test_image_src_resolver_emits_real_img_tag():
    doc = Document(title="T", blocks=[Image(file="image1.png", caption=None)])
    html = emit_body(doc, image_src=lambda f: f"data:image/png;base64,XXX-{f}")
    assert '<img src="data:image/png;base64,XXX-image1.png">' in html
    assert "[[IMG" not in html


def test_image_src_none_keeps_marker():
    doc = Document(title="T", blocks=[Image(file="image1.png", caption=None)])
    html = emit_body(doc)  # no resolver -> marker (VC/Pikabu behavior unchanged)
    assert "[[IMG:image1.png]]" in html


def test_caption_marker_emitted_and_escaped():
    doc = Document(
        title="T",
        blocks=[Image(file="image8.png", caption=[Run("a < b", False, True)])],
    )
    html = emit_body(doc)
    assert "[[IMG:image8.png]]" in html
    assert "[[CAP:a &lt; b]]" in html  # caption text is escaped inside the marker


def test_image_without_caption_emits_no_cap_marker():
    doc = Document(title="T", blocks=[Image(file="image5.png", caption=None)])
    html = emit_body(doc)
    assert "[[IMG:image5.png]]" in html
    assert "[[CAP:" not in html


def test_caption_marker_suppressed_when_disabled():
    # Pikabu has a native caption field, so it pastes the body without CAP markers.
    doc = Document(
        title="T",
        blocks=[Image(file="image8.png", caption=[Run("cap", False, True)])],
    )
    html = emit_body(doc, caption_marker=False)
    assert "[[IMG:image8.png]]" in html
    assert "[[CAP:" not in html


def test_bold_italic_run_nests_both_tags():
    doc = Document(title="T", blocks=[Paragraph(runs=[Run("x", True, True)])])
    html = emit_body(doc)
    assert "<em><strong>x</strong></em>" in html


def test_unordered_list_emits_ul_li():
    doc = Document(title="T", blocks=[ListBlock(ordered=False, items=[
        ListItem(runs=[Run("first", False, False)]),
        ListItem(runs=[Run("second", False, False)]),
    ])])
    html = emit_body(doc)
    assert "<ul><li>first</li><li>second</li></ul>" in html


def test_ordered_list_emits_ol_li_with_formatting():
    doc = Document(title="T", blocks=[ListBlock(ordered=True, items=[
        ListItem(runs=[Run("a ", False, False), Run("bold", True, False)]),
    ])])
    html = emit_body(doc)
    assert "<ol><li>a <strong>bold</strong></li></ol>" in html


def test_quote_emits_blockquote_with_escaping():
    doc = Document(title="T", blocks=[Quote(runs=[Run("q < x", False, False)])])
    html = emit_body(doc)
    assert "<blockquote>q &lt; x</blockquote>" in html


def test_emit_heading_level_3():
    doc = Document(title="t", blocks=[Heading(level=3, runs=[Run("Sub", False, False)])])
    assert "<h3>Sub</h3>" in emit_body(doc)


def test_quote_as_paragraph_mode_renders_p():
    doc = Document(title="T", blocks=[Quote(runs=[Run("q < x", False, False)])])
    html = emit_body(doc, quote_as_paragraph=True)
    assert "<p>q &lt; x</p>" in html
    assert "<blockquote>" not in html


def test_quote_default_still_blockquote():
    doc = Document(title="T", blocks=[Quote(runs=[Run("q", False, False)])])
    assert "<blockquote>q</blockquote>" in emit_body(doc)


def test_max_heading_level_degrades_h3_to_bold_paragraph():
    doc = Document(
        title="T",
        blocks=[
            Heading(level=2, runs=[Run("Sub", False, False)]),
            Heading(level=3, runs=[Run("Deep", False, False)]),
        ],
    )
    html = emit_body(doc, max_heading_level=2)
    assert "<h2>Sub</h2>" in html
    assert "<h3>" not in html
    assert "<p><strong>Deep</strong></p>" in html


def test_max_heading_level_default_keeps_h3():
    doc = Document(title="T", blocks=[Heading(level=3, runs=[Run("Deep", False, False)])])
    html = emit_body(doc)  # no max_heading_level -> unchanged behavior
    assert "<h3>Deep</h3>" in html


def test_max_heading_level_boundary_keeps_cap_degrades_deeper():
    doc = Document(
        title="T",
        blocks=[
            Heading(level=3, runs=[Run("keep", False, False)]),
            Heading(level=4, runs=[Run("drop", False, False)]),
        ],
    )
    html = emit_body(doc, max_heading_level=3)  # h3 kept, h4 degraded
    assert "<h3>keep</h3>" in html
    assert "<h4>" not in html
    assert "<p><strong>drop</strong></p>" in html


def test_max_heading_level_preserves_inline_styles_in_degraded_heading():
    doc = Document(
        title="T",
        blocks=[Heading(level=3, runs=[Run("a ", False, False), Run("b", False, True)])],
    )
    html = emit_body(doc, max_heading_level=2)
    # degraded heading is a bold paragraph; original italics survive nested
    assert "<p><strong>a <em>b</em></strong></p>" in html

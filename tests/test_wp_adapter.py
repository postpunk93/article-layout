# tests/test_wp_adapter.py
from pathlib import Path

from src.adapters import wp
from src.ir import Document, Heading, Paragraph, Quote, Image, ListBlock, ListItem, Run


def test_body_html_emits_native_blocks_data_uri_images_and_caption_markers():
    images_dir = Path("in/synthetic/images")  # real PNGs exist here
    doc = Document(title="T", blocks=[
        Heading(level=2, runs=[Run("Head")]),
        Paragraph(runs=[Run("plain "), Run("bold", bold=True)]),
        ListBlock(ordered=False, items=[ListItem(runs=[Run("one")])]),
        Quote(runs=[Run("quoted")]),
        Image(file="image1.png", caption=[Run("cap one")]),
    ])
    html = wp.body_html(doc, images_dir)

    # Native Gutenberg-friendly structure (paste maps these to core blocks).
    assert "<h2>Head</h2>" in html
    assert "<strong>bold</strong>" in html
    assert "<ul><li>one</li></ul>" in html
    assert "<blockquote>quoted</blockquote>" in html  # NOT a <p> (unlike VC)
    # Images go in as data-URIs (WP sideloads them on paste).
    assert 'src="data:image/png;base64,' in html
    # Captions ride as [[CAP:]] markers for the post-paste cleanup pass.
    assert "[[CAP:cap one]]" in html


def test_constants_point_at_ruminlab():
    assert wp.EDITOR_URL == "https://ruminlab.ru/wp-admin/post-new.php"
    assert wp.ALIVE_SEL == ".editor-document-tools__inserter-toggle"

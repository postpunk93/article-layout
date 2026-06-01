from src.parser import parse
from src.ir import Image, Paragraph

STYLE = "<style>.c0{font-weight:400;font-style:normal}.c3{font-style:italic}</style>"


def _doc(body):
    return parse(f"<html><head>{STYLE}</head><body>{body}</body></html>")


def test_separate_italic_paragraph_after_image_becomes_caption():
    doc = _doc(
        '<p class="c6"><span><img src="images/image1.png"></span></p>'
        '<p class="c6"><span class="c3">Подпись под картинкой</span></p>'
    )
    assert len(doc.blocks) == 1
    assert isinstance(doc.blocks[0], Image)
    assert doc.blocks[0].caption is not None
    assert doc.blocks[0].caption[0].text == "Подпись под картинкой"


def test_separate_normal_paragraph_after_image_stays_paragraph():
    doc = _doc(
        '<p class="c6"><span><img src="images/image1.png"></span></p>'
        '<p class="c6"><span class="c0">Обычный абзац</span></p>'
    )
    assert isinstance(doc.blocks[0], Image)
    assert doc.blocks[0].caption is None
    assert isinstance(doc.blocks[1], Paragraph)
    assert doc.blocks[1].runs[0].text == "Обычный абзац"


def test_second_italic_paragraph_after_captioned_image_is_its_own_paragraph():
    # first italic paragraph attaches as caption; a SECOND italic paragraph does not
    doc = _doc(
        '<p class="c6"><span><img src="images/image1.png"></span></p>'
        '<p class="c6"><span class="c3">Подпись</span></p>'
        '<p class="c6"><span class="c3">Курсивный абзац ниже</span></p>'
    )
    assert isinstance(doc.blocks[0], Image)
    assert doc.blocks[0].caption[0].text == "Подпись"
    assert isinstance(doc.blocks[1], Paragraph)
    assert doc.blocks[1].runs[0].text == "Курсивный абзац ниже"


def test_same_p_caption_not_overridden_by_following_italic_paragraph():
    # image already has a same-<p> caption; a following italic paragraph stays standalone
    doc = _doc(
        '<p class="c6"><span><img src="images/image1.png"></span>'
        '<span><br></span><span class="c3">Подпись в том же абзаце</span></p>'
        '<p class="c6"><span class="c3">Следующий курсивный абзац</span></p>'
    )
    assert doc.blocks[0].caption[0].text == "Подпись в том же абзаце"
    assert isinstance(doc.blocks[1], Paragraph)
    assert doc.blocks[1].runs[0].text == "Следующий курсивный абзац"


def test_italic_paragraph_with_no_preceding_image_stays_paragraph():
    doc = _doc('<p class="c6"><span class="c3">Просто курсивный абзац</span></p>')
    assert len(doc.blocks) == 1
    assert isinstance(doc.blocks[0], Paragraph)


def test_mixed_italic_and_normal_separate_paragraph_is_not_a_caption():
    doc = _doc(
        '<p class="c6"><span><img src="images/image1.png"></span></p>'
        '<p class="c6"><span class="c3">курсив </span><span class="c0">обычный</span></p>'
    )
    assert doc.blocks[0].caption is None  # not ALL runs italic
    assert isinstance(doc.blocks[1], Paragraph)

# tests/test_ir.py
from src.ir import Run, Heading, Paragraph, Image, Document


def test_document_holds_title_and_blocks():
    doc = Document(
        title="My Title",
        blocks=[
            Heading(level=2, runs=[Run("Section", bold=False, italic=False)]),
            Paragraph(runs=[Run("hello ", False, False), Run("world", False, True)]),
            Image(file="image5.png", caption=None),
            Image(file="image8.png", caption=[Run("cap", False, True)]),
        ],
    )
    assert doc.title == "My Title"
    assert doc.blocks[1].runs[1].italic is True
    assert doc.blocks[2].caption is None
    assert doc.blocks[3].caption[0].text == "cap"

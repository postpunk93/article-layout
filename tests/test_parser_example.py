# tests/test_parser_example.py
from pathlib import Path
from src.parser import parse
from src.ir import Image, Heading, Paragraph

doc = parse(Path("tests/fixtures/170/index.html").read_text(encoding="utf-8"))


def test_title_extracted():
    assert "170" in doc.title  # H1 spans "1"/"7"/"0..." merge into the title


def test_all_ten_images_present():
    files = [b.file for b in doc.blocks if isinstance(b, Image)]
    assert sorted(files) == sorted(f"image{i}.png" for i in range(1, 11))


def test_image8_has_italic_caption():
    img8 = next(b for b in doc.blocks if isinstance(b, Image) and b.file == "image8.png")
    assert img8.caption is not None
    assert "набросок" in img8.caption[0].text


def test_image5_has_no_caption():
    img5 = next(b for b in doc.blocks if isinstance(b, Image) and b.file == "image5.png")
    assert img5.caption is None


def test_no_empty_blocks():
    for b in doc.blocks:
        if isinstance(b, (Heading, Paragraph)):
            assert "".join(r.text for r in b.runs).strip() != ""

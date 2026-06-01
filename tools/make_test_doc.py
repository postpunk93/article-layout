"""Generate fixtures/synthetic.docx — a short, all-cases test article authored to our
GDoc conventions. Open it in Google Docs, review, then Download -> HTML into in/synthetic/.

Conventions: Heading 1 = title; Heading 2/3 = headings; yellow highlight = quote;
italic text under an image = caption; bold/italic inline; bulleted + numbered lists.
"""
from pathlib import Path
from docx import Document
from docx.shared import Inches
from docx.enum.text import WD_COLOR_INDEX

FIX = Path("fixtures")


def _tiny_png(path: Path, rgb: tuple[int, int, int]):
    # Minimal solid-color PNG via Pillow if present, else a 1x1 raw fallback.
    try:
        from PIL import Image
        Image.new("RGB", (240, 160), rgb).save(path)
    except ImportError:
        # 1x1 transparent PNG (valid, just tiny) — distinct files still upload fine.
        import base64
        path.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="))


def build():
    FIX.mkdir(exist_ok=True)
    img1, img2 = FIX / "img1.png", FIX / "img2.png"
    _tiny_png(img1, (220, 80, 80))
    _tiny_png(img2, (80, 120, 220))

    doc = Document()
    doc.add_heading("Тестовый документ для вёрстки", level=1)

    p = doc.add_paragraph("Обычный абзац со ")
    p.add_run("жирным").bold = True
    p.add_run(" и ")
    p.add_run("курсивным").italic = True
    p.add_run(" словами.")

    doc.add_heading("Подзаголовок второго уровня", level=2)
    doc.add_paragraph("Короткий абзац под H2 для проверки структуры.")

    doc.add_heading("Подзаголовок третьего уровня", level=3)
    # A connective paragraph so the heading isn't glued straight onto the list.
    doc.add_paragraph("Ниже — маркированный список ключевых пунктов.")
    doc.add_paragraph("Первый пункт", style="List Bullet")
    b = doc.add_paragraph(style="List Bullet")
    b.add_run("Пункт с ")
    b.add_run("жирным").bold = True
    b.add_run(" и ")
    b.add_run("курсивом").italic = True
    doc.add_paragraph("Третий пункт", style="List Bullet")

    # Paragraph between the two lists (italic-only run, for run variety).
    sep = doc.add_paragraph()
    sep.add_run("А теперь те же действия по шагам.").italic = True
    doc.add_paragraph("Первый шаг", style="List Number")
    doc.add_paragraph("Второй шаг", style="List Number")

    # Bold-only paragraph leading into the quote.
    lead = doc.add_paragraph()
    lead.add_run("Важная мысль перед цитатой.").bold = True
    q = doc.add_paragraph()
    qr = q.add_run("Это цитата — выделена жёлтым, должна стать нативным блоком цитаты.")
    qr.font.highlight_color = WD_COLOR_INDEX.YELLOW

    doc.add_paragraph("Дальше идут две иллюстрации с подписями.")
    doc.add_picture(str(img1), width=Inches(2.5))
    cap1 = doc.add_paragraph()
    cap1.add_run("Подпись к первой картинке").italic = True

    # Normal paragraph separating the two images (not italic, so it stays a paragraph,
    # not the caption of image 1 — exercises the separate-paragraph caption boundary).
    doc.add_paragraph("Небольшой комментарий между картинками.")
    doc.add_picture(str(img2), width=Inches(2.5))
    cap2 = doc.add_paragraph()
    cap2.add_run("Подпись ко второй картинке").italic = True

    doc.add_paragraph("Короткий финальный абзац.")

    out = FIX / "synthetic.docx"
    doc.save(str(out))
    print("wrote", out)


if __name__ == "__main__":
    build()

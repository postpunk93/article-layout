import subprocess, sys
from pathlib import Path
from docx import Document
from docx.enum.text import WD_COLOR_INDEX

OUT = Path("fixtures/synthetic.docx")

def test_generator_produces_doc_with_conventions(tmp_path):
    subprocess.run([sys.executable, "tools/make_test_doc.py"], check=True)
    assert OUT.exists()
    doc = Document(str(OUT))
    styles = [p.style.name for p in doc.paragraphs]
    assert "Heading 1" in styles          # title
    assert "Heading 2" in styles and "Heading 3" in styles
    # at least one run is yellow-highlighted (the quote)
    highlighted = [r for p in doc.paragraphs for r in p.runs
                   if r.font.highlight_color == WD_COLOR_INDEX.YELLOW]
    assert highlighted, "expected a yellow-highlighted quote run"
    # at least one bold and one italic run somewhere
    assert any(r.bold for p in doc.paragraphs for r in p.runs)
    assert any(r.italic for p in doc.paragraphs for r in p.runs)

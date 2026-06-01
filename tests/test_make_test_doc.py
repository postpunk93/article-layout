import os
import subprocess, sys
from pathlib import Path
from docx import Document
from docx.enum.text import WD_COLOR_INDEX


def test_generator_produces_doc_with_conventions(tmp_path):
    # Generate into tmp_path (via SYNTHETIC_OUT_DIR) so the run does not overwrite
    # the committed fixtures/synthetic.docx (python-docx output isn't byte-stable).
    env = {**os.environ, "SYNTHETIC_OUT_DIR": str(tmp_path)}
    subprocess.run([sys.executable, "tools/make_test_doc.py"], check=True, env=env)
    out = tmp_path / "synthetic.docx"
    assert out.exists()
    doc = Document(str(out))
    styles = [p.style.name for p in doc.paragraphs]
    assert "Heading 1" in styles          # title
    assert "Heading 2" in styles and "Heading 3" in styles
    assert len(doc.inline_shapes) == 2    # two images
    assert "List Bullet" in styles and "List Number" in styles
    # at least one run is yellow-highlighted (the quote)
    highlighted = [r for p in doc.paragraphs for r in p.runs
                   if r.font.highlight_color == WD_COLOR_INDEX.YELLOW]
    assert highlighted, "expected a yellow-highlighted quote run"
    # at least one bold and one italic run somewhere
    assert any(r.bold for p in doc.paragraphs for r in p.runs)
    assert any(r.italic for p in doc.paragraphs for r in p.runs)

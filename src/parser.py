# src/parser.py
import re
from bs4 import BeautifulSoup

from src.ir import Run, Heading, Paragraph, Document


def style_class_sets(html: str):
    """Return (italic_classes, bold_classes) by scanning the <style> block.

    A class is italic if its rule contains font-style:italic.
    A class is bold if its rule contains font-weight:700.
    """
    soup = BeautifulSoup(html, "html.parser")
    css = "\n".join(s.get_text() for s in soup.find_all("style"))
    italic, bold = set(), set()
    for name, body in re.findall(r"\.(c\d+)\s*\{([^}]*)\}", css):
        decls = re.sub(r"\s+", "", body)
        if "font-style:italic" in decls:
            italic.add(name)
        if "font-weight:700" in decls:
            bold.add(name)
    return italic, bold


def _span_style(span, italic_classes, bold_classes):
    classes = span.get("class", []) if hasattr(span, "get") else []
    italic = any(c in italic_classes for c in classes)
    bold = any(c in bold_classes for c in classes)
    return bold, italic


def spans_to_runs(block, italic_classes, bold_classes):
    """Flatten a block's <span> children into merged Run objects.

    Adjacent runs with identical (bold, italic) are concatenated.
    <br>-only spans contribute no text. Empty text is skipped.
    """
    runs = []
    for span in block.find_all("span", recursive=False):
        text = span.get_text()  # decodes entities; a <br>-only span yields ""
        if not text:
            continue
        bold, italic = _span_style(span, italic_classes, bold_classes)
        if runs and runs[-1].bold == bold and runs[-1].italic == italic:
            runs[-1].text += text
        else:
            runs.append(Run(text=text, bold=bold, italic=italic))
    # drop whitespace-only runs, but keep a single inter-word space
    runs = [r for r in runs if r.text.strip() != "" or r.text == " "]
    return runs


def _runs_text(runs):
    return "".join(r.text for r in runs).strip()


def parse(html: str) -> Document:
    italic_classes, bold_classes = style_class_sets(html)
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    title = ""
    blocks = []
    for el in body.find_all(["h1", "h2", "p"], recursive=True):
        if el.find("img") is not None:
            continue  # images handled in Task 6
        runs = spans_to_runs(el, italic_classes, bold_classes)
        if not runs:
            continue
        if el.name == "h1":
            if not title:
                title = _runs_text(runs)
            continue
        if el.name == "h2":
            blocks.append(Heading(level=2, runs=runs))
        else:
            blocks.append(Paragraph(runs=runs))
    return Document(title=title, blocks=blocks)

# src/parser.py
import os
import re
from bs4 import BeautifulSoup

from src.ir import Run, Heading, Paragraph, Image, ListItem, ListBlock, Quote, Document


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


def yellow_class_set(html: str):
    """Return the set of CSS classes whose rule sets background-color:#ffff00."""
    soup = BeautifulSoup(html, "html.parser")
    css = "\n".join(s.get_text() for s in soup.find_all("style"))
    yellow = set()
    for name, body in re.findall(r"\.(c\d+)\s*\{([^}]*)\}", css):
        if "background-color:#ffff00" in re.sub(r"\s+", "", body):
            yellow.add(name)
    return yellow


def _is_yellow_quote(p, yellow_classes):
    """True if every non-empty direct <span> of p carries a yellow class."""
    spans = [s for s in p.find_all("span", recursive=False) if s.get_text().strip()]
    if not spans:
        return False
    return all(any(c in yellow_classes for c in s.get("class", [])) for s in spans)


def _span_style(span, italic_classes, bold_classes):
    classes = span.get("class", []) if hasattr(span, "get") else []
    italic = any(c in italic_classes for c in classes)
    bold = any(c in bold_classes for c in classes)
    return bold, italic


def _merge_spans(spans, italic_classes, bold_classes):
    """Merge an iterable of <span> tags into styled Runs.

    Adjacent runs with identical (bold, italic) are concatenated.
    Empty spans contribute nothing; whitespace-only runs are dropped
    except a single inter-word space.
    """
    runs = []
    for span in spans:
        text = span.get_text()
        if not text:
            continue
        bold, italic = _span_style(span, italic_classes, bold_classes)
        if runs and runs[-1].bold == bold and runs[-1].italic == italic:
            runs[-1].text += text
        else:
            runs.append(Run(text=text, bold=bold, italic=italic))
    return [r for r in runs if r.text.strip() != "" or r.text == " "]


def spans_to_runs(block, italic_classes, bold_classes):
    """Flatten a block's direct-child <span> elements into merged Runs."""
    return _merge_spans(block.find_all("span", recursive=False), italic_classes, bold_classes)


def _trailing_runs_after_img(p, italic_classes, bold_classes):
    """Runs from spans that appear AFTER the <img> within the same <p>."""
    trailing = []
    after = False
    for span in p.find_all("span", recursive=False):
        if span.find("img") is not None:
            after = True
            continue
        if after:
            trailing.append(span)
    return _merge_spans(trailing, italic_classes, bold_classes)


def _runs_text(runs):
    return "".join(r.text for r in runs).strip()


def _parse_list(el, italic_classes, bold_classes):
    """Turn a <ul>/<ol> into a ListBlock. Inline formatting preserved per item;
    empty items dropped."""
    items = []
    for li in el.find_all("li", recursive=False):
        runs = _merge_spans(li.find_all("span", recursive=False), italic_classes, bold_classes)
        if runs:
            items.append(ListItem(runs=runs))
    return ListBlock(ordered=(el.name == "ol"), items=items)


def parse(html: str) -> Document:
    italic_classes, bold_classes = style_class_sets(html)
    yellow_classes = yellow_class_set(html)
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    title = ""
    blocks = []
    for el in body.find_all(["h1", "h2", "p", "ul", "ol"], recursive=False):
        if el.name in ("ul", "ol"):
            lb = _parse_list(el, italic_classes, bold_classes)
            if lb.items:
                blocks.append(lb)
            continue
        if el.find("img") is not None:
            img = el.find("img")
            file = os.path.basename(img.get("src", ""))
            trailing = _trailing_runs_after_img(el, italic_classes, bold_classes)
            if trailing and all(r.italic for r in trailing):
                blocks.append(Image(file=file, caption=trailing))
            else:
                blocks.append(Image(file=file, caption=None))
                if trailing:
                    blocks.append(Paragraph(runs=trailing))
            continue
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
            if el.name == "p" and _is_yellow_quote(el, yellow_classes):
                blocks.append(Quote(runs=runs))
                continue
            blocks.append(Paragraph(runs=runs))
    return Document(title=title, blocks=blocks)

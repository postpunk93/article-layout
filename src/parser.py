# src/parser.py
import os
import re
from bs4 import BeautifulSoup

from src.ir import Run, Heading, Paragraph, Image, ListItem, ListBlock, Quote, Document


def _iter_class_rules(html: str):
    """Yield (class_name, whitespace-stripped rule body) for each .cN{...} rule
    across all <style> blocks."""
    soup = BeautifulSoup(html, "html.parser")
    css = "\n".join(s.get_text() for s in soup.find_all("style"))
    for name, body in re.findall(r"\.(c\d+)\s*\{([^}]*)\}", css):
        yield name, re.sub(r"\s+", "", body)


def style_class_sets(html: str):
    """Return (italic_classes, bold_classes) by scanning the <style> block.

    A class is italic if its rule contains font-style:italic.
    A class is bold if its rule contains font-weight:700.
    """
    italic, bold = set(), set()
    for name, decls in _iter_class_rules(html):
        if "font-style:italic" in decls:
            italic.add(name)
        if "font-weight:700" in decls:
            bold.add(name)
    return italic, bold


def yellow_class_set(html: str):
    """Return the set of CSS classes whose rule sets background-color:#ffff00."""
    yellow = set()
    for name, decls in _iter_class_rules(html):
        if "background-color:#ffff00" in decls:
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
    empty items dropped.

    v1 assumption: each <li>'s text lives in <span> children directly under the
    <li> (as the observed GDoc export produces). Items whose spans are wrapped
    in a child block, and nested <ul>/<ol> inside an <li>, are not handled —
    they would yield no runs and be silently dropped (flat-lists-only scope)."""
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
    for el in body.find_all(["h1", "h2", "h3", "p", "ul", "ol"], recursive=False):
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
        if el.name in ("h2", "h3"):
            blocks.append(Heading(level=int(el.name[1]), runs=runs))
        else:
            if el.name == "p" and _is_yellow_quote(el, yellow_classes):
                blocks.append(Quote(runs=runs))
                continue
            # A standalone, all-italic paragraph immediately after a caption-less image is
            # its caption (GDoc emits the image alone in its <p> and the caption as the next
            # <p> when the image sits on its own line — the same-<p> form is handled above).
            if (blocks and isinstance(blocks[-1], Image)
                    and blocks[-1].caption is None
                    and all(r.italic for r in runs)):
                blocks[-1].caption = runs
                continue
            blocks.append(Paragraph(runs=runs))
    return Document(title=title, blocks=blocks)

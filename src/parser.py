# src/parser.py
import re
from bs4 import BeautifulSoup


def style_class_sets(html: str):
    """Return (italic_classes, bold_classes) by scanning the <style> block.

    A class is italic if its rule contains font-style:italic.
    A class is bold if its rule contains font-weight:700.
    """
    soup = BeautifulSoup(html, "html.parser")
    style = soup.find("style")
    css = style.get_text() if style else ""
    italic, bold = set(), set()
    for name, body in re.findall(r"\.(c\d+)\s*\{([^}]*)\}", css):
        decls = body.replace(" ", "")
        if "font-style:italic" in decls:
            italic.add(name)
        if "font-weight:700" in decls:
            bold.add(name)
    return italic, bold

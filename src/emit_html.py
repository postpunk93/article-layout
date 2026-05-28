# src/emit_html.py
from html import escape
from src.ir import Heading, Paragraph, Image


def _runs_html(runs):
    out = []
    for r in runs:
        text = escape(r.text)
        if r.bold:
            text = f"<strong>{text}</strong>"
        if r.italic:
            text = f"<em>{text}</em>"
        out.append(text)
    return "".join(out)


def emit_body(doc):
    """Render IR blocks to clean body HTML.

    Images are NOT emitted as <img>; they become a visible marker
    paragraph [[IMG:file]] that the VC adapter later replaces with a
    real uploaded image. Captions are emitted as a marker too so the
    adapter can attach them after upload.
    """
    parts = []
    for b in doc.blocks:
        if isinstance(b, Heading):
            parts.append(f"<h{b.level}>{_runs_html(b.runs)}</h{b.level}>")
        elif isinstance(b, Paragraph):
            parts.append(f"<p>{_runs_html(b.runs)}</p>")
        elif isinstance(b, Image):
            parts.append(f"<p>[[IMG:{b.file}]]</p>")
            if b.caption:
                cap = "".join(r.text for r in b.caption)
                parts.append(f"<p>[[CAP:{escape(cap)}]]</p>")
    return "\n".join(parts)

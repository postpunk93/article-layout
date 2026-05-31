# src/emit_html.py
from html import escape
from src.ir import Heading, Paragraph, Image, ListBlock, Quote


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


def emit_body(doc, caption_marker=True, quote_as_paragraph=False, img_sep=":",
              max_heading_level=None, image_src=None):
    """Render IR blocks to clean body HTML.

    Images are NOT emitted as <img>; they become a visible marker
    paragraph [[IMG<sep>file]] that the adapter later replaces with a
    real uploaded image.

    Captions are emitted as a [[CAP:text]] marker by default so an adapter
    can read them from the body. Platforms whose image block has a NATIVE
    caption field (e.g. Pikabu) pass ``caption_marker=False`` and instead set
    the caption straight from the IR — no marker paragraph is produced.

    Pass ``quote_as_paragraph=True`` (e.g. VC) to render quotes as ``<p>`` so
    they survive a lossy paste and are converted to quote blocks afterwards.

    ``img_sep`` is the separator inside the image marker. Default ``":"`` gives
    ``[[IMG:file]]``. VC pastes via the real clipboard and its editor treats
    ``IMG:file.png`` as a ``scheme:path`` link, which ABORTS the multi-block
    paste — VC passes ``img_sep=" "`` (``[[IMG file]]``) to dodge that.

    ``max_heading_level`` caps the subheading depth: a ``Heading`` deeper than
    this level (e.g. Habr supports only ``h2``) degrades to a bold paragraph
    ``<p><strong>…</strong></p>`` instead of an ``<hN>`` tag. Default ``None``
    means no cap — every heading keeps its native level.
    """
    parts = []
    for b in doc.blocks:
        if isinstance(b, Heading):
            if max_heading_level is not None and b.level > max_heading_level:
                # Habr has one subheading level: a deeper heading degrades to a
                # bold line (keep any inner italics) rather than an <hN> tag.
                parts.append(f"<p><strong>{_runs_html(b.runs)}</strong></p>")
            else:
                parts.append(f"<h{b.level}>{_runs_html(b.runs)}</h{b.level}>")
        elif isinstance(b, Paragraph):
            parts.append(f"<p>{_runs_html(b.runs)}</p>")
        elif isinstance(b, ListBlock):
            tag = "ol" if b.ordered else "ul"
            items = "".join(f"<li>{_runs_html(it.runs)}</li>" for it in b.items)
            parts.append(f"<{tag}>{items}</{tag}>")
        elif isinstance(b, Quote):
            tag = "p" if quote_as_paragraph else "blockquote"
            parts.append(f"<{tag}>{_runs_html(b.runs)}</{tag}>")
        elif isinstance(b, Image):
            if image_src is not None:
                # Emit a real <img> (e.g. a data-URI). Habr auto-uploads it to its
                # CDN on paste, so no marker/replace pass is needed. Escape the src
                # for safety even though a data-URI carries no special chars.
                parts.append(f'<p><img src="{escape(image_src(b.file), quote=True)}"></p>')
            else:
                # file is a basename lookup key for the adapter; intentionally not escaped
                parts.append(f"<p>[[IMG{img_sep}{b.file}]]</p>")
            if caption_marker and b.caption:
                cap = "".join(r.text for r in b.caption)
                parts.append(f"<p>[[CAP:{escape(cap)}]]</p>")
    return "\n".join(parts)

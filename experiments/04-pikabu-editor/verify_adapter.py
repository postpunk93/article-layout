"""End-to-end check of the Pikabu adapter, dumped to JSON (no eyeballing needed).

No arg: builds a small synthetic Document (heading, paragraph, image+caption, lists,
quote, image w/o caption, paragraph) — confirms order, uploads, captions, cleanup.

With an arg (a slug dir like in/lists-quotes): parses the real GDoc export and runs
the full article, then dumps the editor structure + an IR-vs-editor block-count check.

Run: python experiments/04-pikabu-editor/verify_adapter.py [in/<slug>]
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from src.ir import Document, Heading, Paragraph, Image, ListBlock, ListItem, Quote, Run
from src.parser import parse
from src import pikabu_adapter as A

OUT = Path("experiments/04-pikabu-editor/verify_adapter.json")
IMAGES_DIR = Path("example/lists-quotes/images")

DOC = Document(
    title="Проверка адаптера Pikabu",
    blocks=[
        Heading(level=2, runs=[Run("Заголовок раздела")]),
        Paragraph(runs=[Run("Обычный "), Run("жирный", bold=True), Run(" и "),
                        Run("курсив", italic=True), Run(" текст.")]),
        Image(file="image1.png", caption=[Run("Подпись к первой картинке")]),
        Paragraph(runs=[Run("Абзац между картинками.")]),
        ListBlock(ordered=False, items=[
            ListItem(runs=[Run("первый пункт")]),
            ListItem(runs=[Run("второй пункт")]),
        ]),
        ListBlock(ordered=True, items=[
            ListItem(runs=[Run("раз")]),
            ListItem(runs=[Run("два")]),
        ]),
        Quote(runs=[Run("Цитата для проверки.")]),
        Image(file="image2.png", caption=None),
        Paragraph(runs=[Run("Финальный абзац.")]),
    ],
)


def dump_structure(page):
    return page.evaluate(
        """() => {
            const PLACEHOLDER = 'Введите описание';  // shown when caption is empty
            return [...document.querySelector('.tiptap.ProseMirror').children].map(c => {
                const img = c.querySelector('img');
                const txt = (c.innerText || '').trim();
                return {
                    tag: c.querySelector('h2') ? 'h2'
                       : img ? 'image'
                       : c.querySelector('ul') ? 'ul'
                       : c.querySelector('ol') ? 'ol'
                       : c.querySelector('blockquote') ? 'blockquote'
                       : 'p',
                    text: txt.slice(0, 60),
                    imgSrc: img ? (img.currentSrc || img.src || '').slice(0, 55) : null,
                    // for an image block the only text IS the caption (or placeholder)
                    caption: (img && !txt.includes(PLACEHOLDER)) ? txt : null,
                };
            }).filter(b => b.text !== '' || b.imgSrc);
        }"""
    )


def main():
    report = {}
    if len(sys.argv) > 1:
        slug = Path(sys.argv[1])
        doc = parse((slug / "index.html").read_text(encoding="utf-8"))
        images_dir = slug / "images"
    else:
        doc, images_dir = DOC, IMAGES_DIR
    report["ir_blocks"] = len(doc.blocks)
    report["ir_images"] = sum(1 for b in doc.blocks if isinstance(b, Image))
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            A.PROFILE_DIR, headless=False, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            A.build_document(page, doc, images_dir)
            page.wait_for_timeout(1500)
            report["structure"] = dump_structure(page)
            report["url"] = page.url
            report["markers_left"] = page.evaluate(
                "() => document.querySelector('.tiptap.ProseMirror').innerText.includes('[[IMG:')"
            )
            report["img_count"] = page.evaluate(
                "() => document.querySelectorAll('.tiptap.ProseMirror img').length"
            )
        finally:
            OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print("Wrote", OUT)
            print("url:", report.get("url"))
            print(f"IR blocks={report.get('ir_blocks')} images={report.get('ir_images')} | "
                  f"editor img_count={report.get('img_count')} markers_left={report.get('markers_left')}")
            # stdout may be cp1251 (Windows) — keep the per-block dump ASCII-safe.
            print("structure (captions = filled image caption text, else None):")
            for b in report.get("structure", []):
                cap = b.get("caption")
                line = f"   {b['tag']:>10} img={'Y' if b.get('imgSrc') else '-'} cap={'Y' if cap else '-'}"
                print(line.encode("ascii", "replace").decode())
            ctx.close()


if __name__ == "__main__":
    main()

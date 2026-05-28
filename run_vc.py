"""Usage: python run_vc.py in/<slug>

Parses the unpacked Google Docs export in the given folder and drives the VC
editor to a saved draft. The browser stays open for manual review/publishing.
"""
import sys
from pathlib import Path

from src.parser import parse
from src import vc_adapter


def main():
    if len(sys.argv) != 2:
        print("Usage: python run_vc.py in/<slug>")
        raise SystemExit(2)
    slug_dir = Path(sys.argv[1])
    index = slug_dir / "index.html"
    if not index.exists():
        print(f"Not found: {index}")
        raise SystemExit(1)

    doc = parse(index.read_text(encoding="utf-8"))
    referenced = [b.file for b in doc.blocks if hasattr(b, "file")]
    images_dir = slug_dir / "images"
    on_disk = {p.name for p in images_dir.glob("*")} if images_dir.exists() else set()
    missing = [f for f in referenced if f not in on_disk]
    if missing:
        print(f"WARNING: referenced images not found in {images_dir}: {missing}")

    print(f"Parsed: title={doc.title!r}, blocks={len(doc.blocks)}, images={len(referenced)}")
    vc_adapter.run_document(images_dir, doc)


if __name__ == "__main__":
    main()

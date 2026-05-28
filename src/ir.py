# src/ir.py
from dataclasses import dataclass, field


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False


@dataclass
class Heading:
    level: int
    runs: list = field(default_factory=list)


@dataclass
class Paragraph:
    runs: list = field(default_factory=list)


@dataclass
class Image:
    file: str
    caption: list | None = None  # list[Run] or None


@dataclass
class Document:
    title: str
    blocks: list = field(default_factory=list)

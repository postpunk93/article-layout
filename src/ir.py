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
    runs: list[Run] = field(default_factory=list)


@dataclass
class Paragraph:
    runs: list[Run] = field(default_factory=list)


@dataclass
class Image:
    file: str
    caption: list[Run] | None = None


@dataclass
class ListItem:
    runs: list[Run] = field(default_factory=list)


@dataclass
class ListBlock:
    ordered: bool
    items: list[ListItem] = field(default_factory=list)


@dataclass
class Quote:
    runs: list[Run] = field(default_factory=list)


@dataclass
class Document:
    title: str
    blocks: list["Heading | Paragraph | Image | ListBlock | Quote"] = field(default_factory=list)

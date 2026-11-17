"""The common output of every parser: a document split into heading-scoped sections.

Invariant (tested for every parser): content[s.char_start:s.char_end] == s.text.
Offsets are therefore always valid positions in the stored document text, which is
what powers click-to-view citations later.
"""

from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Literal

DocFormat = Literal["markdown", "pdf", "text"]


class UnsupportedFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Section:
    heading_path: tuple[str, ...]
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class PageSpan:
    page: int  # 1-based
    char_start: int
    char_end: int


@dataclass(frozen=True)
class ParsedDocument:
    format: DocFormat
    content: str
    sections: list[Section]
    title: str | None = None
    # Only for paginated formats (PDF); sorted by char_start.
    pages: list[PageSpan] = field(default_factory=list)

    @property
    def page_count(self) -> int | None:
        return len(self.pages) or None

    def pages_for(self, char_start: int, char_end: int) -> tuple[int | None, int | None]:
        """Page range covering [char_start, char_end), or (None, None) if unpaginated."""
        if not self.pages:
            return None, None
        starts = [p.char_start for p in self.pages]
        first = self.pages[max(bisect_right(starts, char_start) - 1, 0)].page
        last = self.pages[max(bisect_right(starts, max(char_end - 1, char_start)) - 1, 0)].page
        return first, last


def make_section(
    content: str, start: int, end: int, heading_path: tuple[str, ...]
) -> Section | None:
    """Build a section for content[start:end], trimmed of surrounding whitespace.

    Returns None when the span is blank (e.g. a heading directly followed by another).
    """
    while start < end and content[start].isspace():
        start += 1
    while end > start and content[end - 1].isspace():
        end -= 1
    if start >= end:
        return None
    return Section(heading_path, content[start:end], start, end)


def decode_text(data: bytes) -> str:
    """Decode bytes as UTF-8 (BOM tolerated), falling back to Latin-1, normalizing newlines."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return text.replace("\r\n", "\n").replace("\r", "\n")

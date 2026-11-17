"""Pick a parser by file extension."""

from pathlib import PurePath

from lorvo.ingest.parsers.base import ParsedDocument, UnsupportedFormatError
from lorvo.ingest.parsers.markdown import parse_markdown
from lorvo.ingest.parsers.pdf import parse_pdf
from lorvo.ingest.parsers.text import parse_text

_PARSERS = {
    ".md": parse_markdown,
    ".markdown": parse_markdown,
    ".txt": parse_text,
    ".text": parse_text,
    ".pdf": parse_pdf,
}

SUPPORTED_EXTENSIONS = frozenset(_PARSERS)


def parse(data: bytes, filename: str) -> ParsedDocument:
    ext = PurePath(filename).suffix.lower()
    try:
        parser = _PARSERS[ext]
    except KeyError:
        raise UnsupportedFormatError(f"unsupported file type: {ext or filename!r}") from None
    return parser(data)


__all__ = ["SUPPORTED_EXTENSIONS", "ParsedDocument", "UnsupportedFormatError", "parse"]

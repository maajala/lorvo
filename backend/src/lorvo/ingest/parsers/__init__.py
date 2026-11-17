"""Pick a parser by file extension."""

from pathlib import PurePath

from lorvo.ingest.parsers.base import ParsedDocument, UnsupportedFormatError
from lorvo.ingest.parsers.markdown import parse_markdown

_PARSERS = {
    ".md": parse_markdown,
    ".markdown": parse_markdown,
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

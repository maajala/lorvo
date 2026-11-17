"""Plain-text parser: the whole file is one section; the chunker splits it by size."""

from lorvo.ingest.parsers.base import ParsedDocument, decode_text, make_section


def parse_text(data: bytes) -> ParsedDocument:
    content = decode_text(data)
    section = make_section(content, 0, len(content), ())
    return ParsedDocument(format="text", content=content, sections=[section] if section else [])

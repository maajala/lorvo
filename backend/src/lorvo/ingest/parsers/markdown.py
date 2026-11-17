"""Markdown parser: sections are the text between headings; content is the file verbatim."""

import re

from markdown_it import MarkdownIt
from markdown_it.token import Token

from lorvo.ingest.parsers.base import ParsedDocument, Section, decode_text, make_section

_FRONT_MATTER = re.compile(r"\A---\n.*?\n(?:---|\.\.\.)\n", re.DOTALL)
_md = MarkdownIt("commonmark").enable("table")


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            offsets.append(i + 1)
    offsets.append(len(text))  # sentinel so offsets[n_lines] is valid
    return offsets


def _plain(inline: Token) -> str:
    """Heading text without markup: '**Time** `off`' -> 'Time off'."""
    parts = [c.content for c in inline.children or [] if c.type in ("text", "code_inline")]
    return " ".join("".join(parts).split()) or inline.content.strip()


def parse_markdown(data: bytes) -> ParsedDocument:
    content = decode_text(data)

    # YAML front matter is metadata, not body text; skip it but keep offsets absolute.
    fm = _FRONT_MATTER.match(content)
    body_start = fm.end() if fm else 0
    lines = _line_offsets(content)
    first_body_line = content.count("\n", 0, body_start)

    tokens = _md.parse(content[body_start:])

    # (line_start, line_end, level, text) for each heading, in document order.
    headings: list[tuple[int, int, int, str]] = []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open" and tok.map:
            level = int(tok.tag[1])
            text = _plain(tokens[i + 1])
            headings.append(
                (tok.map[0] + first_body_line, tok.map[1] + first_body_line, level, text)
            )

    sections: list[Section] = []
    stack: list[tuple[int, str]] = []  # (level, text)

    def emit(start: int, end: int) -> None:
        sec = make_section(content, start, end, tuple(t for _, t in stack))
        if sec:
            sections.append(sec)

    # Preamble before the first heading.
    first_heading_line = headings[0][0] if headings else len(lines) - 1
    emit(body_start, lines[first_heading_line])

    for idx, (_, h_end, level, text) in enumerate(headings):
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, text))
        next_start = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines) - 1
        emit(lines[h_end], lines[next_start])

    title = next((t for _, _, lvl, t in headings if lvl == 1), None)
    return ParsedDocument(format="markdown", content=content, sections=sections, title=title)

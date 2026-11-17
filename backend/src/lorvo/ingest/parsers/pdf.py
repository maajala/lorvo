"""PDF parser (PyMuPDF). Headings are inferred from font size and boldness.

The body font size is the most common size weighted by character count; lines
clearly larger than it, or short all-bold lines, are headings. Distinct heading
styles are ranked by size to get heading levels.
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import pymupdf

from lorvo.ingest.parsers.base import PageSpan, ParsedDocument, Section, make_section

# PyMuPDF is only partially typed; keep the untyped surface behind one Any boundary.
_fitz: Any = pymupdf

_PAGE_NUMBER = re.compile(r"^(page\s*)?\d+(\s*(of|/)\s*\d+)?$", re.IGNORECASE)
_BOLD_FLAG = 16
_SIZE_RATIO = 1.15
_MAX_HEADING_CHARS = 120


@dataclass
class _Line:
    page: int
    block: int
    text: str
    size: float
    bold: bool


def _extract_lines(doc: Any) -> list[_Line]:
    out: list[_Line] = []
    for page_no, page in enumerate(doc, start=1):
        for b_idx, block in enumerate(page.get_text("dict", sort=True)["blocks"]):
            if block.get("type") != 0:  # 0 = text; images etc. are skipped
                continue
            for line in block["lines"]:
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = " ".join("".join(s["text"] for s in spans).split())
                if _PAGE_NUMBER.match(text):  # running page numbers are noise
                    continue
                size = max(s["size"] for s in spans)
                bold = all(s["flags"] & _BOLD_FLAG or "bold" in s["font"].lower() for s in spans)
                out.append(_Line(page_no, b_idx, text, round(size * 2) / 2, bold))
    return out


def _heading_levels(lines: list[_Line]) -> dict[tuple[float, bool], int]:
    """Map (size, bold) styles that look like headings to levels 1..n."""
    weights: Counter[float] = Counter()
    for ln in lines:
        weights[ln.size] += len(ln.text)
    if not weights:
        return {}
    body = weights.most_common(1)[0][0]

    styles: set[tuple[float, bool]] = set()
    for ln in lines:
        if len(ln.text) > _MAX_HEADING_CHARS or not any(c.isalpha() for c in ln.text):
            continue
        bigger = ln.size >= body * _SIZE_RATIO
        bold_label = (
            ln.bold
            and ln.size >= body
            and len(ln.text.split()) <= 12
            and not ln.text.endswith((".", ",", ";", ":"))
        )
        if bigger or bold_label:
            styles.add((ln.size, ln.bold))
    ranked = sorted(styles, key=lambda st: (-st[0], not st[1]))
    return {st: i + 1 for i, st in enumerate(ranked)}


def parse_pdf(data: bytes) -> ParsedDocument:
    with _fitz.open(stream=data, filetype="pdf") as doc:
        meta_title = (doc.metadata or {}).get("title") or None
        n_pages = doc.page_count
        lines = _extract_lines(doc)

    levels = _heading_levels(lines)

    # Build the stored text: lines joined by \n, blocks/pages separated by a blank line.
    parts: list[str] = []
    offsets: list[tuple[int, int]] = []  # (start, end) of each line in content
    pos = 0
    prev: _Line | None = None
    for ln in lines:
        if prev is not None:
            sep = "\n" if (ln.page, ln.block) == (prev.page, prev.block) else "\n\n"
            parts.append(sep)
            pos += len(sep)
        parts.append(ln.text)
        offsets.append((pos, pos + len(ln.text)))
        pos += len(ln.text)
        prev = ln
    content = "".join(parts)

    pages: list[PageSpan] = []
    for page_no in range(1, n_pages + 1):
        idx = [i for i, ln in enumerate(lines) if ln.page == page_no]
        if idx:
            pages.append(PageSpan(page_no, offsets[idx[0]][0], offsets[idx[-1]][1]))

    sections: list[Section] = []
    stack: list[tuple[int, str]] = []
    body_start = 0
    pending_heading: tuple[int, int] | None = None  # (line index, level) of the last heading

    def emit(end: int) -> None:
        sec = make_section(content, body_start, end, tuple(t for _, t in stack))
        if sec:
            sections.append(sec)

    for i, ln in enumerate(lines):
        level = levels.get((ln.size, ln.bold))
        if level is None:
            continue
        # A heading that wraps onto a second line in the same block: merge them.
        if pending_heading and pending_heading == (i - 1, level) and lines[i - 1].block == ln.block:
            stack[-1] = (level, f"{stack[-1][1]} {ln.text}")
            body_start = offsets[i][1]
            pending_heading = (i, level)
            continue
        emit(offsets[i][0])
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, ln.text))
        body_start = offsets[i][1]
        pending_heading = (i, level)
    emit(len(content))

    first_h1 = next((t for t in (s.heading_path[:1] for s in sections) if t), None)
    title = meta_title or (first_h1[0] if first_h1 else None)
    return ParsedDocument(
        format="pdf", content=content, sections=sections, title=title, pages=pages
    )

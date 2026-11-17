"""Structure-first chunking.

1. Each parsed section is a chunk if it fits the token budget.
2. Longer sections are split recursively: paragraphs, then sentences, then words,
   and the pieces are packed greedily up to the budget.
3. Consecutive chunks overlap by whole trailing pieces (never mid-sentence).
4. Chunk text is always an exact slice of the document text, so offsets stay valid.

The text that gets *embedded* is prefixed with a contextual header (title +
heading path), so "Submit the form 2 weeks in advance" still matches "how do I
request a day off?". The budget includes that header, so embedded inputs stay
under the embedding model's max sequence length.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from lorvo.ingest.parsers.base import ParsedDocument, Section

TokenCounter = Callable[[str], int]

_PARAGRAPH = re.compile(r"\n[ \t]*\n\s*")
_SENTENCE = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])|\n")
_WORD = re.compile(r"\s+")
_SEPARATORS = (_PARAGRAPH, _SENTENCE, _WORD)
_MIN_BODY_BUDGET = 32


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    text: str
    embed_text: str
    heading_path: tuple[str, ...]
    char_start: int
    char_end: int
    page_start: int | None
    page_end: int | None
    token_count: int  # tokens in embed_text


@dataclass(frozen=True)
class ChunkerConfig:
    target_tokens: int = 350
    overlap_tokens: int = 50

    def fingerprint(self) -> str:
        return f"chunker-v1:t{self.target_tokens}:o{self.overlap_tokens}"


Span = tuple[int, int]


def contextual_header(title: str | None, heading_path: tuple[str, ...]) -> str:
    parts = list(heading_path)
    if title and (not parts or parts[0] != title):
        parts.insert(0, title)
    return " > ".join(parts)


def _strip_span(content: str, start: int, end: int) -> Span | None:
    while start < end and content[start].isspace():
        start += 1
    while end > start and content[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None


def _split_on(content: str, span: Span, sep: re.Pattern[str]) -> list[Span]:
    start, end = span
    pieces: list[Span] = []
    cursor = start
    for m in sep.finditer(content, start, end):
        piece = _strip_span(content, cursor, m.start())
        if piece:
            pieces.append(piece)
        cursor = m.end()
    tail = _strip_span(content, cursor, end)
    if tail:
        pieces.append(tail)
    return pieces


def _hard_split(span: Span, max_chars: int) -> list[Span]:
    start, end = span
    return [(i, min(i + max_chars, end)) for i in range(start, end, max_chars)]


class Chunker:
    def __init__(self, count_tokens: TokenCounter, config: ChunkerConfig | None = None) -> None:
        self.count = count_tokens
        self.config = config or ChunkerConfig()

    def chunk(self, doc: ParsedDocument, title: str | None = None) -> list[ChunkDraft]:
        title = title or doc.title
        drafts: list[ChunkDraft] = []
        for section in doc.sections:
            header = contextual_header(title, section.heading_path)
            for start, end in self._split_section(doc.content, section, header):
                text = doc.content[start:end]
                embed_text = f"{header}\n\n{text}" if header else text
                page_start, page_end = doc.pages_for(start, end)
                drafts.append(
                    ChunkDraft(
                        ordinal=len(drafts),
                        text=text,
                        embed_text=embed_text,
                        heading_path=section.heading_path,
                        char_start=start,
                        char_end=end,
                        page_start=page_start,
                        page_end=page_end,
                        token_count=self.count(embed_text),
                    )
                )
        return drafts

    # ------------------------------------------------------------------ internals

    def _split_section(self, content: str, section: Section, header: str) -> list[Span]:
        header_tokens = self.count(header) + 2 if header else 0
        budget = max(self.config.target_tokens - header_tokens, _MIN_BODY_BUDGET)
        span = (section.char_start, section.char_end)
        if self.count(section.text) <= budget:
            return [span]
        pieces = self._pieces(content, span, budget, level=0)
        return self._pack(pieces, budget)

    def _pieces(self, content: str, span: Span, budget: int, level: int) -> list[tuple[Span, int]]:
        """Split span into (piece, token_count) pairs, each within budget if possible."""
        if level >= len(_SEPARATORS):
            # A single "word" longer than the budget (e.g. a base64 blob): cut by chars.
            return [(s, self.count(content[s[0] : s[1]])) for s in _hard_split(span, budget * 3)]
        out: list[tuple[Span, int]] = []
        for piece in _split_on(content, span, _SEPARATORS[level]):
            n = self.count(content[piece[0] : piece[1]])
            if n <= budget:
                out.append((piece, n))
            else:
                out.extend(self._pieces(content, piece, budget, level + 1))
        return out

    def _pack(self, pieces: list[tuple[Span, int]], budget: int) -> list[Span]:
        overlap_budget = self.config.overlap_tokens
        chunks: list[Span] = []
        current: list[tuple[Span, int]] = []
        size = 0

        for piece, n in pieces:
            if current and size + n > budget:
                chunks.append((current[0][0][0], current[-1][0][1]))
                # Carry trailing pieces forward as overlap, but never the whole chunk
                # (that would stall) and never so much that the next piece won't fit.
                carry: list[tuple[Span, int]] = []
                carried = 0
                for prev in reversed(current[1:]):
                    if carried + prev[1] > overlap_budget or carried + prev[1] + n > budget:
                        break
                    carry.insert(0, prev)
                    carried += prev[1]
                current, size = carry, carried
            current.append((piece, n))
            size += n

        if current:
            chunks.append((current[0][0][0], current[-1][0][1]))
        return chunks

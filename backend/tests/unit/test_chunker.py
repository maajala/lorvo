import itertools

from lorvo.ingest.chunker import Chunker, ChunkerConfig, contextual_header
from lorvo.ingest.parsers.base import PageSpan, ParsedDocument, Section
from lorvo.ingest.parsers.markdown import parse_markdown


def words(text: str) -> int:
    return len(text.split())


def single_section_doc(text: str, path: tuple[str, ...] = ("Guide",)) -> ParsedDocument:
    return ParsedDocument(format="text", content=text, sections=[Section(path, text, 0, len(text))])


def sentence(i: int) -> str:
    return f"Sentence number {i} explains one small policy detail clearly."  # 8 words


def test_small_section_is_one_chunk_with_contextual_header() -> None:
    doc = parse_markdown(b"# Handbook\n## Time Off\nSubmit the form 2 weeks in advance.\n")
    [chunk] = Chunker(words).chunk(doc)
    assert chunk.text == "Submit the form 2 weeks in advance."
    assert chunk.heading_path == ("Handbook", "Time Off")
    assert chunk.embed_text == "Handbook > Time Off\n\nSubmit the form 2 weeks in advance."
    assert chunk.token_count == words(chunk.embed_text)


def test_title_is_prefixed_when_not_in_heading_path() -> None:
    assert contextual_header("leave.txt", ()) == "leave.txt"
    assert contextual_header("Handbook", ("Handbook", "A")) == "Handbook > A"
    assert contextual_header("Policies", ("A",)) == "Policies > A"
    assert contextual_header(None, ()) == ""


def test_huge_section_respects_budget_overlaps_and_covers_everything() -> None:
    paragraphs = [" ".join(sentence(p * 10 + s) for s in range(3)) for p in range(40)]
    text = "\n\n".join(paragraphs)
    cfg = ChunkerConfig(target_tokens=100, overlap_tokens=30)
    chunks = Chunker(words, cfg).chunk(single_section_doc(text))

    assert len(chunks) > 5
    for c in chunks:
        assert c.token_count <= cfg.target_tokens
        assert text[c.char_start : c.char_end] == c.text
    for a, b in itertools.pairwise(chunks):
        assert b.char_start < a.char_end, "consecutive chunks should overlap"
        assert b.char_start > a.char_start, "chunking must make progress"
    for p in paragraphs:
        assert any(p in c.text for c in chunks)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_long_paragraph_splits_on_sentence_boundaries() -> None:
    text = " ".join(sentence(i) for i in range(60))  # one paragraph, 480 words
    chunks = Chunker(words, ChunkerConfig(100, 20)).chunk(single_section_doc(text))
    assert len(chunks) > 1
    for c in chunks:
        assert c.text.startswith("Sentence number")
        assert c.text.endswith(".")


def test_giant_unbreakable_token_terminates() -> None:
    text = "x" * 5000
    chunks = Chunker(lambda s: len(s) // 4 + 1, ChunkerConfig(64, 8)).chunk(
        single_section_doc(text, ())
    )
    assert "".join(c.text for c in chunks) == text


def test_empty_document() -> None:
    assert Chunker(words).chunk(ParsedDocument(format="text", content="", sections=[])) == []


def test_page_ranges_follow_offsets() -> None:
    page1 = "Alpha. " * 40
    page2 = "Beta. " * 40
    content = page1 + "\n\n" + page2
    doc = ParsedDocument(
        format="pdf",
        content=content,
        sections=[Section((), content, 0, len(content))],
        pages=[
            PageSpan(1, 0, len(page1)),
            PageSpan(2, len(page1) + 2, len(content)),
        ],
    )
    chunks = Chunker(words, ChunkerConfig(40, 0)).chunk(doc, title="Report")
    assert chunks[0].page_start == chunks[0].page_end == 1
    assert chunks[-1].page_start == chunks[-1].page_end == 2
    assert all(c.embed_text.startswith("Report\n\n") for c in chunks)

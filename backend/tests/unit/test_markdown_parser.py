import pytest

from lorvo.ingest.parsers import UnsupportedFormatError, parse
from lorvo.ingest.parsers.base import ParsedDocument
from lorvo.ingest.parsers.markdown import parse_markdown

HANDBOOK = b"""\
---
title: ignored front matter
---
Welcome text before any heading.

# Employee Handbook

Intro to the handbook.

## Time Off

### Requesting Leave

Submit the form **2 weeks** in advance.

```bash
# not a heading, just a comment
echo hi
```

### Sick Days
Call your manager.

## Expenses
Keep receipts.
"""


def assert_offsets_valid(doc: ParsedDocument) -> None:
    for s in doc.sections:
        assert doc.content[s.char_start : s.char_end] == s.text


def test_heading_paths_and_title() -> None:
    doc = parse_markdown(HANDBOOK)
    assert doc.title == "Employee Handbook"
    assert [s.heading_path for s in doc.sections] == [
        (),
        ("Employee Handbook",),
        ("Employee Handbook", "Time Off", "Requesting Leave"),
        ("Employee Handbook", "Time Off", "Sick Days"),
        ("Employee Handbook", "Expenses"),
    ]
    assert_offsets_valid(doc)


def test_code_block_comment_is_not_a_heading() -> None:
    doc = parse_markdown(HANDBOOK)
    leave = doc.sections[2]
    assert "# not a heading" in leave.text
    assert leave.text.startswith("Submit the form")


def test_front_matter_is_skipped() -> None:
    doc = parse_markdown(HANDBOOK)
    assert "front matter" not in doc.sections[0].text
    assert doc.sections[0].text == "Welcome text before any heading."


def test_heading_markup_is_stripped() -> None:
    doc = parse_markdown(b"# The `lorvo` **CLI**\n\nbody\n")
    assert doc.sections[0].heading_path == ("The lorvo CLI",)


def test_setext_headings_and_crlf() -> None:
    doc = parse_markdown(b"Title\r\n=====\r\n\r\nBody one.\r\n\r\nSub\r\n---\r\nBody two.\r\n")
    assert [(s.heading_path, s.text) for s in doc.sections] == [
        (("Title",), "Body one."),
        (("Title", "Sub"), "Body two."),
    ]
    assert_offsets_valid(doc)


def test_empty_and_heading_only_files() -> None:
    assert parse_markdown(b"").sections == []
    assert parse_markdown(b"# Only\n## Headings\n").sections == []


def test_no_headings_is_one_section() -> None:
    doc = parse_markdown(b"just some text\n\nand more\n")
    assert len(doc.sections) == 1
    assert doc.sections[0].heading_path == ()
    assert doc.title is None


def test_dispatch_by_extension() -> None:
    assert parse(b"# A\nb", "notes.MD").format == "markdown"
    with pytest.raises(UnsupportedFormatError):
        parse(b"", "photo.png")

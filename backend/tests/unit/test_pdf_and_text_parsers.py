from lorvo.ingest.parsers import parse
from lorvo.ingest.parsers.pdf import parse_pdf
from lorvo.ingest.parsers.text import parse_text
from tests.pdf_factory import make_pdf
from tests.unit.test_markdown_parser import assert_offsets_valid

BODY = 11.0


def test_pdf_headings_from_font_size_and_bold() -> None:
    data = make_pdf(
        [
            [
                ("Employee Handbook", 20, True),
                ("Welcome to the company.", BODY, False),
                ("Time Off", 15, True),
                ("Requesting Leave", BODY, True),
                ("Submit the form two weeks in advance.", BODY, False),
            ],
            [
                ("Sick Days", BODY, True),
                ("Call your manager before 9am.", BODY, False),
                ("2", 9, False),  # page number noise
            ],
        ]
    )
    doc = parse_pdf(data)
    assert doc.title == "Employee Handbook"
    assert doc.page_count == 2
    assert [(s.heading_path, s.text) for s in doc.sections] == [
        (("Employee Handbook",), "Welcome to the company."),
        (
            ("Employee Handbook", "Time Off", "Requesting Leave"),
            "Submit the form two weeks in advance.",
        ),
        (("Employee Handbook", "Time Off", "Sick Days"), "Call your manager before 9am."),
    ]
    assert_offsets_valid(doc)
    sick = doc.sections[2]
    assert doc.pages_for(sick.char_start, sick.char_end) == (2, 2)
    assert "\n2\n" not in doc.content


def test_pdf_without_headings_is_one_section_spanning_pages() -> None:
    data = make_pdf(
        [[("First page body text.", BODY, False)], [("Second page body text.", BODY, False)]],
        title="Plain Report",
    )
    doc = parse_pdf(data)
    assert doc.title == "Plain Report"
    assert len(doc.sections) == 1
    s = doc.sections[0]
    assert s.heading_path == ()
    assert doc.pages_for(s.char_start, s.char_end) == (1, 2)
    assert_offsets_valid(doc)


def test_bold_sentence_is_not_a_heading() -> None:
    data = make_pdf([[("Important: read this whole sentence carefully.", BODY, True)]])
    assert parse_pdf(data).sections[0].heading_path == ()


def test_empty_pdf_has_no_sections() -> None:
    doc = parse_pdf(make_pdf([[]]))
    assert doc.sections == []
    assert doc.pages_for(0, 0) == (None, None)


def test_text_parser() -> None:
    doc = parse_text(b"\xef\xbb\xbfline one\r\n\r\nline two\n")
    assert doc.sections[0].text == "line one\n\nline two"
    assert_offsets_valid(doc)
    assert parse_text(b"   \n").sections == []
    assert parse_text("caf\xe9".encode("latin-1")).content == "café"


def test_dispatch() -> None:
    assert parse(b"x", "a.txt").format == "text"
    assert parse(make_pdf([[("x", BODY, False)]]), "a.PDF").format == "pdf"

"""Build small PDFs in-memory for tests (no binary fixtures in the repo)."""

from typing import Any

import pymupdf

_fitz: Any = pymupdf

Line = tuple[str, float, bool]  # text, font size, bold


def make_pdf(pages: list[list[Line]], title: str | None = None) -> bytes:
    doc = _fitz.open()
    for lines in pages:
        page = doc.new_page()
        y = 72.0
        for text, size, bold in lines:
            page.insert_text((72, y), text, fontsize=size, fontname="hebo" if bold else "helv")
            y += size * 1.8
    if title:
        doc.set_metadata({"title": title})
    data: bytes = doc.tobytes()
    doc.close()
    return data

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from lorvo.cli import app
from lorvo.config import get_settings
from lorvo.db.models import Chunk, Document
from lorvo.ingest.chunker import ChunkerConfig
from lorvo.ingest.embedder import FakeEmbedder
from lorvo.ingest.pipeline import IngestPipeline
from tests.pdf_factory import make_pdf

HANDBOOK = """# Employee Handbook

## Time Off

### Requesting Leave

Submit the leave form in the HR portal at least 2 weeks in advance.

### Sick Days

Tell your manager before 9am.
"""


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    (tmp_path / "handbook.md").write_text(HANDBOOK)
    (tmp_path / "notes.txt").write_text("Office wifi password rotates monthly.")
    (tmp_path / "policy.pdf").write_bytes(
        make_pdf([[("Expenses", 18, True), ("Keep all receipts for 90 days.", 11, False)]])
    )
    (tmp_path / "image.png").write_bytes(b"\x89PNG")  # unsupported: ignored
    (tmp_path / ".hidden.md").write_text("# secret")  # hidden: ignored
    return tmp_path


def pipeline(sf: sessionmaker[Session], target: int = 350) -> IngestPipeline:
    return IngestPipeline(sf, FakeEmbedder(), ChunkerConfig(target, 20))


def count(session: Session, model: type[Document] | type[Chunk]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_ingest_folder_then_skip_unchanged(
    docs: Path, session_factory: sessionmaker[Session], session: Session
) -> None:
    first = pipeline(session_factory).ingest_path(docs)
    assert sorted((r.filename, r.status) for r in first) == [
        ("handbook.md", "ingested"),
        ("notes.txt", "ingested"),
        ("policy.pdf", "ingested"),
    ]
    assert count(session, Document) == 3

    leave = session.scalars(
        select(Chunk).where(Chunk.heading_path.contains(["Requesting Leave"]))
    ).one()
    assert leave.heading_path == ["Employee Handbook", "Time Off", "Requesting Leave"]
    assert leave.document.content[leave.char_start : leave.char_end] == leave.text

    pdf_chunk = session.scalars(select(Chunk).where(Chunk.text.contains("receipts"))).one()
    assert (pdf_chunk.page_start, pdf_chunk.page_end) == (1, 1)

    second = pipeline(session_factory).ingest_path(docs)
    assert {r.status for r in second} == {"skipped"}


def test_changed_file_replaces_its_chunks(
    docs: Path, session_factory: sessionmaker[Session], session: Session
) -> None:
    p = pipeline(session_factory)
    p.ingest_path(docs)
    before = count(session, Chunk)

    (docs / "handbook.md").write_text(HANDBOOK + "\n## Expenses\n\nUse the company card.\n")
    results = {r.filename: r for r in p.ingest_path(docs)}
    assert results["handbook.md"].status == "updated"
    assert results["notes.txt"].status == "skipped"
    assert count(session, Document) == 3
    assert count(session, Chunk) == before + 1


def test_chunker_settings_change_forces_reingest(
    docs: Path, session_factory: sessionmaker[Session]
) -> None:
    pipeline(session_factory).ingest_path(docs)
    results = pipeline(session_factory, target=200).ingest_path(docs)
    assert {r.status for r in results} == {"updated"}


def test_empty_and_corrupt_files_fail_without_aborting(
    tmp_path: Path, session_factory: sessionmaker[Session], session: Session
) -> None:
    (tmp_path / "a_empty.md").write_text("")
    (tmp_path / "b_broken.pdf").write_bytes(b"not a pdf")
    (tmp_path / "c_ok.txt").write_text("fine")
    results = {r.filename: r for r in pipeline(session_factory).ingest_path(tmp_path)}
    assert results["a_empty.md"].status == "failed"
    assert results["b_broken.pdf"].status == "failed"
    assert results["c_ok.txt"].status == "ingested"
    assert count(session, Document) == 1


def test_cli_ingest(
    docs: Path, db_url: str, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("EMBEDDER", "fake")
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(app, ["ingest", str(docs)])
        assert result.exit_code == 0, result.output
        assert "3 files: 3 ingested, 0 updated, 0 skipped, 0 failed" in result.output

        again = CliRunner().invoke(app, ["ingest", str(docs)])
        assert "0 ingested, 0 updated, 3 skipped" in again.output
    finally:
        get_settings.cache_clear()

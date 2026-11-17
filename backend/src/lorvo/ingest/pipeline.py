"""parse -> chunk -> embed -> store, idempotently.

Each document is identified by a stable `source` string. A file is skipped when
both its SHA-256 and the pipeline fingerprint (embedder + chunker settings) are
unchanged; otherwise its chunks are replaced in a single transaction.

Embedding (the slow part) happens *before* the write transaction opens, so the
transaction is short and readers never see a half-replaced document.
"""

import hashlib
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from lorvo.db.models import Chunk, Document
from lorvo.ingest.chunker import Chunker, ChunkerConfig
from lorvo.ingest.embedder import Embedder
from lorvo.ingest.parsers import SUPPORTED_EXTENSIONS, UnsupportedFormatError, parse

log = logging.getLogger(__name__)

Status = Literal["ingested", "updated", "skipped", "failed"]


@dataclass(frozen=True)
class IngestResult:
    source: str
    filename: str
    status: Status
    chunks: int = 0
    document_id: str | None = None
    error: str | None = None


class IngestPipeline:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        embedder: Embedder,
        chunker_config: ChunkerConfig | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.embedder = embedder
        self.chunker_config = chunker_config or ChunkerConfig()
        self.chunker = Chunker(embedder.count_tokens, self.chunker_config)
        self.fingerprint = hashlib.sha256(
            f"{embedder.name}|{self.chunker_config.fingerprint()}".encode()
        ).hexdigest()

    # ----------------------------------------------------------------- public API

    def ingest_bytes(self, data: bytes, filename: str, source: str) -> IngestResult:
        sha = hashlib.sha256(data).hexdigest()

        with self.session_factory() as s:
            existing = s.scalar(select(Document).where(Document.source == source))
            if (
                existing is not None
                and existing.sha256 == sha
                and existing.pipeline_fingerprint == self.fingerprint
            ):
                return IngestResult(
                    source, filename, "skipped", len(existing.chunks), str(existing.id)
                )

        try:
            parsed = parse(data, filename)
        except UnsupportedFormatError as e:
            return IngestResult(source, filename, "failed", error=str(e))
        except Exception as e:  # corrupt PDFs etc. must not abort a folder ingest
            log.exception("failed to parse %s", source)
            return IngestResult(source, filename, "failed", error=f"could not parse file: {e}")

        if not parsed.sections:
            return IngestResult(
                source, filename, "failed", error="no extractable text (empty or scanned file?)"
            )

        title = parsed.title or Path(filename).stem
        drafts = self.chunker.chunk(parsed, title=title)
        vectors = self.embedder.embed_documents([d.embed_text for d in drafts])

        with self.session_factory.begin() as s:
            doc = s.scalar(select(Document).where(Document.source == source).with_for_update())
            status: Status
            if doc is None:
                doc = Document(source=source)
                s.add(doc)
                status = "ingested"
            else:
                s.execute(delete(Chunk).where(Chunk.document_id == doc.id))
                status = "updated"

            doc.filename = filename
            doc.format = parsed.format
            doc.title = title
            doc.sha256 = sha
            doc.pipeline_fingerprint = self.fingerprint
            doc.size_bytes = len(data)
            doc.content = parsed.content
            doc.page_count = parsed.page_count
            s.flush()  # assigns doc.id for new documents

            s.add_all(
                Chunk(
                    document_id=doc.id,
                    ordinal=d.ordinal,
                    text=d.text,
                    heading_path=list(d.heading_path),
                    char_start=d.char_start,
                    char_end=d.char_end,
                    page_start=d.page_start,
                    page_end=d.page_end,
                    token_count=d.token_count,
                    embedding=v,
                )
                for d, v in zip(drafts, vectors, strict=True)
            )
            doc_id = str(doc.id)

        return IngestResult(source, filename, status, len(drafts), doc_id)

    def ingest_path(self, path: Path) -> list[IngestResult]:
        """Ingest one file, or every supported file under a directory (recursively)."""
        return [
            self.ingest_bytes(f.read_bytes(), f.name, source=str(f.resolve()))
            for f in iter_supported_files(path)
        ]


def iter_supported_files(path: Path) -> Iterator[Path]:
    if path.is_file():
        yield path
        return
    for f in sorted(path.rglob("*")):
        rel_parts = f.relative_to(path).parts
        if any(part.startswith(".") for part in rel_parts):
            continue  # skip hidden files and dirs (.git, .DS_Store, ...)
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield f

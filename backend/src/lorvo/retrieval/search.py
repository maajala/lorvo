"""Vector search over chunks (cosine similarity via pgvector's HNSW index)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from lorvo.db.models import Chunk, Document
from lorvo.ingest.embedder import Embedder


@dataclass(frozen=True)
class SearchHit:
    chunk_id: int
    document_id: uuid.UUID
    filename: str
    title: str | None
    text: str
    heading_path: list[str]
    score: float  # cosine similarity in [-1, 1]; higher is more relevant
    char_start: int
    char_end: int
    page_start: int | None
    page_end: int | None


def search(session: Session, embedder: Embedder, query: str, k: int = 5) -> list[SearchHit]:
    qvec = embedder.embed_query(query)
    distance = Chunk.embedding.cosine_distance(qvec).label("distance")
    rows = session.execute(
        select(Chunk, Document.filename, Document.title, distance)
        .join(Document, Chunk.document_id == Document.id)
        .order_by(distance)
        .limit(k)
    ).all()
    return [
        SearchHit(
            chunk_id=c.id,
            document_id=c.document_id,
            filename=filename,
            title=title,
            text=c.text,
            heading_path=list(c.heading_path),
            score=1.0 - float(dist),
            char_start=c.char_start,
            char_end=c.char_end,
            page_start=c.page_start,
            page_end=c.page_end,
        )
        for c, filename, title, dist in rows
    ]

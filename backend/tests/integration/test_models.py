import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from lorvo.db.models import EMBEDDING_DIM, Chunk, Document


def _unit(i: int) -> list[float]:
    v = [0.0] * EMBEDDING_DIM
    v[i] = 1.0
    return v


def _doc(source: str) -> Document:
    return Document(
        source=source,
        filename=source,
        format="text",
        sha256=hashlib.sha256(source.encode()).hexdigest(),
        pipeline_fingerprint="test",
        size_bytes=10,
        content="hello world",
    )


def test_cosine_nearest_neighbour_and_cascade_delete(session: Session) -> None:
    doc = _doc("a.txt")
    doc.chunks = [
        Chunk(
            ordinal=i,
            text=f"chunk {i}",
            heading_path=["A", f"S{i}"],
            char_start=0,
            char_end=5,
            token_count=2,
            embedding=_unit(i),
        )
        for i in range(3)
    ]
    session.add(doc)
    session.commit()

    nearest = session.scalars(
        select(Chunk).order_by(Chunk.embedding.cosine_distance(_unit(2))).limit(1)
    ).one()
    assert nearest.text == "chunk 2"
    assert nearest.heading_path == ["A", "S2"]

    session.delete(doc)
    session.commit()
    assert session.scalars(select(Chunk)).all() == []

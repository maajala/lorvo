from typing import Annotated

from fastapi import APIRouter, Query

from lorvo.api.deps import EmbedderDep, SessionDep
from lorvo.api.schemas import SearchHitOut, SearchOut
from lorvo.retrieval.search import search

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchOut)
def search_chunks(
    session: SessionDep,
    embedder: EmbedderDep,
    q: Annotated[str, Query(min_length=1, max_length=1000, description="Natural-language query")],
    k: Annotated[int, Query(ge=1, le=50)] = 5,
) -> SearchOut:
    """Top-k chunks by semantic similarity: retrieval only, no LLM yet."""
    hits = search(session, embedder, q, k)
    return SearchOut(query=q, results=[SearchHitOut.model_validate(h) for h in hits])

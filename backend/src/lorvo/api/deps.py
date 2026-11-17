"""FastAPI dependencies. Tests swap these via app.dependency_overrides."""

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session, sessionmaker

from lorvo.config import Settings, get_settings
from lorvo.db.session import default_session_factory
from lorvo.ingest.chunker import ChunkerConfig
from lorvo.ingest.embedder import Embedder, build_embedder
from lorvo.ingest.pipeline import IngestPipeline


def get_session_factory() -> sessionmaker[Session]:
    return default_session_factory()


def get_session(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> Iterator[Session]:
    with factory() as session:
        yield session


@lru_cache
def _embedder() -> Embedder:
    # Loaded once per process; the local model takes a couple of seconds to load.
    return build_embedder(get_settings())


def get_embedder() -> Embedder:
    return _embedder()


def get_pipeline(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> IngestPipeline:
    cfg = ChunkerConfig(settings.chunk_target_tokens, settings.chunk_overlap_tokens)
    return IngestPipeline(factory, embedder, cfg)


SessionDep = Annotated[Session, Depends(get_session)]
EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
PipelineDep = Annotated[IngestPipeline, Depends(get_pipeline)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

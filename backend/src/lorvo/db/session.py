"""Engine and session helpers."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from lorvo.config import get_settings


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@lru_cache
def default_session_factory() -> sessionmaker[Session]:
    return make_session_factory(make_engine(get_settings().database_url))


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with default_session_factory()() as session:
        yield session

"""Integration fixtures: a real Postgres+pgvector database, migrated with Alembic.

Tests here are skipped unless TEST_DATABASE_URL is set (env or .env). CI sets it.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from lorvo.db.session import make_engine, make_session_factory

BACKEND_DIR = Path(__file__).resolve().parents[2]


class _TestEnv(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", ".env"), extra="ignore"
    )
    test_database_url: str | None = None


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration" in str(item.path):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def db_url() -> str:
    url = _TestEnv().test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL not set; run `docker compose up -d db` and set it in .env")
    return url


@pytest.fixture(scope="session")
def engine(db_url: str) -> Iterator[Engine]:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.attributes["configure_logger"] = False
    # Migrate from scratch each run so the migrations themselves are tested.
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng = make_engine(db_url)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE documents CASCADE"))
    return make_session_factory(engine)


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as s:
        yield s

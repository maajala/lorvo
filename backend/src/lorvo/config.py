"""Application settings, loaded from environment variables (and an optional .env file).

Secrets only ever come from the environment; nothing here has a real default key.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/lorvo/config.py -> repo root. A missing .env is simply ignored.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://lorvo:lorvo@localhost:5432/lorvo"

    embedder: Literal["local", "fake"] = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    chunk_target_tokens: int = Field(default=350, ge=32, le=480)
    chunk_overlap_tokens: int = Field(default=50, ge=0)

    max_upload_bytes: int = 20 * 1024 * 1024

    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5-5"

    @model_validator(mode="after")
    def _overlap_smaller_than_target(self) -> "Settings":
        if self.chunk_overlap_tokens >= self.chunk_target_tokens // 2:
            raise ValueError("chunk_overlap_tokens must be less than half of chunk_target_tokens")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

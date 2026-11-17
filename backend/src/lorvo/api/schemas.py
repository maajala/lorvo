"""Response models for the HTTP API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    title: str | None
    format: str
    size_bytes: int
    page_count: int | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class IngestOut(BaseModel):
    status: str
    document_id: uuid.UUID | None
    filename: str
    chunks: int


class SearchHitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: int
    document_id: uuid.UUID
    filename: str
    title: str | None
    heading_path: list[str]
    text: str
    score: float
    char_start: int
    char_end: int
    page_start: int | None
    page_end: int | None


class SearchOut(BaseModel):
    query: str
    results: list[SearchHitOut]

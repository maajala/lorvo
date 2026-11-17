import uuid
from pathlib import PurePath

from fastapi import APIRouter, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select

from lorvo.api.deps import PipelineDep, SessionDep, SettingsDep
from lorvo.api.schemas import DocumentOut, IngestOut
from lorvo.db.models import Chunk, Document
from lorvo.ingest.parsers import SUPPORTED_EXTENSIONS

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=IngestOut, responses={201: {}, 413: {}, 415: {}, 422: {}})
def upload_document(
    file: UploadFile, pipeline: PipelineDep, settings: SettingsDep, response: Response
) -> IngestOut:
    """Upload a PDF / Markdown / text file. Re-uploading the same filename replaces it."""
    filename = PurePath(file.filename or "").name  # never trust client paths
    if PurePath(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File too large")

    result = pipeline.ingest_bytes(data, filename, source=f"upload:{filename}")
    if result.status == "failed":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, result.error)
    if result.status == "ingested":
        response.status_code = status.HTTP_201_CREATED
    return IngestOut(
        status=result.status,
        document_id=uuid.UUID(result.document_id) if result.document_id else None,
        filename=filename,
        chunks=result.chunks,
    )


@router.get("", response_model=list[DocumentOut])
def list_documents(session: SessionDep) -> list[DocumentOut]:
    chunk_count = (
        select(func.count(Chunk.id)).where(Chunk.document_id == Document.id).scalar_subquery()
    )
    rows = session.execute(
        select(Document, chunk_count.label("n")).order_by(Document.filename)
    ).all()
    return [
        DocumentOut(
            id=d.id,
            filename=d.filename,
            title=d.title,
            format=d.format,
            size_bytes=d.size_bytes,
            page_count=d.page_count,
            chunk_count=n,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d, n in rows
    ]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: uuid.UUID, session: SessionDep) -> None:
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    session.delete(doc)  # chunks go with it (ON DELETE CASCADE)
    session.commit()

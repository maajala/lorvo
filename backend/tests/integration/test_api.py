from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from lorvo.api.deps import get_embedder, get_session_factory
from lorvo.ingest.embedder import FakeEmbedder
from lorvo.main import create_app
from tests.pdf_factory import make_pdf

LEAVE_MD = b"""# Employee Handbook
## Time Off
### Requesting Leave
Submit the leave request in the HR portal at least two weeks in advance.
## Expenses
Expense reports need itemised receipts.
"""


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_embedder] = FakeEmbedder
    with TestClient(app) as c:
        yield c


def upload(client: TestClient, name: str, data: bytes) -> dict[str, object]:
    r = client.post("/documents", files={"file": (name, data)})
    assert r.status_code in (200, 201), r.text
    body: dict[str, object] = r.json()
    return body


def test_upload_list_search_delete(client: TestClient) -> None:
    created = upload(client, "handbook.md", LEAVE_MD)
    assert created["status"] == "ingested"
    upload(client, "policy.pdf", make_pdf([[("Travel", 18, True), ("Book economy.", 11, False)]]))

    docs = client.get("/documents").json()
    assert [d["filename"] for d in docs] == ["handbook.md", "policy.pdf"]
    assert docs[0]["title"] == "Employee Handbook"
    assert docs[0]["chunk_count"] == 2
    assert docs[1]["page_count"] == 1

    r = client.get("/search", params={"q": "leave request two weeks advance", "k": 2})
    assert r.status_code == 200
    top = r.json()["results"][0]
    assert top["filename"] == "handbook.md"
    assert top["heading_path"] == ["Employee Handbook", "Time Off", "Requesting Leave"]
    assert top["text"].startswith("Submit the leave request")
    assert 0 < top["score"] <= 1
    assert top["char_end"] > top["char_start"]

    assert client.delete(f"/documents/{created['document_id']}").status_code == 204
    assert [d["filename"] for d in client.get("/documents").json()] == ["policy.pdf"]
    assert client.delete(f"/documents/{created['document_id']}").status_code == 404


def test_reupload_is_idempotent_and_replaces_changes(client: TestClient) -> None:
    first = upload(client, "handbook.md", LEAVE_MD)
    assert upload(client, "handbook.md", LEAVE_MD)["status"] == "skipped"
    changed = upload(client, "handbook.md", LEAVE_MD + b"## Travel\nBook economy.\n")
    assert changed["status"] == "updated"
    assert changed["document_id"] == first["document_id"]
    assert changed["chunks"] == 3


def test_upload_rejections(client: TestClient) -> None:
    r = client.post("/documents", files={"file": ("x.exe", b"MZ")})
    assert r.status_code == 415
    r = client.post("/documents", files={"file": ("empty.md", b"")})
    assert r.status_code == 422
    r = client.post("/documents", files={"file": ("../../etc/evil.md", b"# Hi\nthere")})
    assert r.json()["filename"] == "evil.md"


def test_search_validation_and_empty_index(client: TestClient) -> None:
    assert client.get("/search", params={"q": ""}).status_code == 422
    assert client.get("/search", params={"q": "x", "k": 0}).status_code == 422
    assert client.get("/search", params={"q": "anything"}).json()["results"] == []
    assert client.get("/health").json() == {"status": "ok"}

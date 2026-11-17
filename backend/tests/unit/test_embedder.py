import math

import pytest

from lorvo.config import Settings
from lorvo.db.models import EMBEDDING_DIM
from lorvo.ingest.embedder import FakeEmbedder, build_embedder


def cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_fake_embedder_is_deterministic_and_normalized() -> None:
    e = FakeEmbedder()
    [a] = e.embed_documents(["Request time off two weeks ahead"])
    assert a == e.embed_query("Request time off two weeks ahead")
    assert len(a) == EMBEDDING_DIM
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0)


def test_fake_embedder_shared_words_are_closer() -> None:
    e = FakeEmbedder()
    q = e.embed_query("how do I request time off")
    leave, expenses = e.embed_documents(
        ["To request time off, submit the form.", "Expense reports need receipts."]
    )
    assert cos(q, leave) > cos(q, expenses)


def test_fake_embedder_empty_text_is_not_zero_vector() -> None:
    assert any(FakeEmbedder().embed_query(""))


def test_build_embedder_from_settings() -> None:
    s = Settings(_env_file=None, embedder="fake")  # type: ignore[call-arg]
    assert build_embedder(s).name.startswith("fake")


@pytest.mark.slow
def test_local_embedder_semantic_similarity() -> None:
    pytest.importorskip("sentence_transformers")
    from lorvo.ingest.embedder import LocalEmbedder

    e = LocalEmbedder()
    assert e.dim == EMBEDDING_DIM
    q = e.embed_query("How do I request a day off?")
    leave, wifi = e.embed_documents(
        [
            "Time Off > Requesting Leave\n\nSubmit the leave form 2 weeks in advance.",
            "IT > Wi-Fi\n\nThe guest network password rotates monthly.",
        ]
    )
    assert cos(q, leave) > cos(q, wifi)
    assert e.count_tokens("hello world") >= 2

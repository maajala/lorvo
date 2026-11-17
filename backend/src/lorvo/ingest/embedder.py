"""Embedders turn text into vectors. All implementations share one small protocol.

- LocalEmbedder: BAAI/bge-small-en-v1.5 via sentence-transformers (384 dims, runs on
  Apple Silicon via MPS, no API key). Installed with `uv sync --extra local`.
- FakeEmbedder: deterministic hashed bag-of-words vectors. Texts sharing words get
  similar vectors, so retrieval tests are meaningful without downloading a model.

Queries and documents are embedded differently: BGE models expect an instruction
prefix on short retrieval queries but not on passages.
"""

import hashlib
import importlib
import math
import re
from collections.abc import Sequence
from typing import Any, Protocol

from lorvo.config import Settings
from lorvo.db.models import EMBEDDING_DIM

BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
_TOKEN = re.compile(r"\w+|[^\w\s]")


class Embedder(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def count_tokens(self, text: str) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FakeEmbedder:
    """Hashed bag-of-words. Deterministic, fast, and good enough for tests."""

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self._dim = dim

    @property
    def name(self) -> str:
        return f"fake-hash-{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def count_tokens(self, text: str) -> int:
        return len(_TOKEN.findall(text))

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for word in re.findall(r"\w+", text.lower()):
            h = int.from_bytes(hashlib.sha256(word.encode()).digest()[:8], "big")
            vec[h % self._dim] += 1.0 if (h >> 32) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            vec[0] = 1.0  # pgvector cosine distance is undefined for zero vectors
            return vec
        return [v / norm for v in vec]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class LocalEmbedder:
    """sentence-transformers model run locally (MPS on Apple Silicon, else CUDA/CPU)."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", batch_size: int = 32) -> None:
        try:
            st: Any = importlib.import_module("sentence_transformers")
        except ImportError as e:  # pragma: no cover - depends on installed extras
            raise RuntimeError(
                "LocalEmbedder needs the 'local' extra: run `uv sync --extra local`, "
                "or set EMBEDDER=fake for tests."
            ) from e
        self._model_name = model_name
        self._batch_size = batch_size
        self._model: Any = st.SentenceTransformer(model_name)
        self._dim = int(self._model.get_embedding_dimension())
        self._query_prefix = BGE_QUERY_INSTRUCTION if "bge" in model_name.lower() else ""

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def max_tokens(self) -> int:
        return int(self._model.max_seq_length)

    def count_tokens(self, text: str) -> int:
        ids = self._model.tokenizer(text, add_special_tokens=True, verbose=False)["input_ids"]
        return len(ids)

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        out = self._model.encode(
            list(texts),
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(x) for x in row] for row in out]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self._query_prefix + text])[0]


def build_embedder(settings: Settings) -> Embedder:
    embedder: Embedder
    if settings.embedder == "fake":
        embedder = FakeEmbedder()
    else:
        embedder = LocalEmbedder(settings.embedding_model)
    if embedder.dim != EMBEDDING_DIM:
        raise ValueError(
            f"{embedder.name} produces {embedder.dim}-dim vectors but the database column is "
            f"vector({EMBEDDING_DIM}); add a migration before switching models."
        )
    return embedder

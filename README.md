# Lorvo

**An AI assistant that answers questions about your team's documents, and cites its sources.**

Ask *"How do I request a day off?"* and Lorvo answers by quoting the exact policy
section, with a link to the original passage. If the documents don't contain the
answer, it says so instead of making one up.

> **Status:** step 1 of 5 is complete: ingestion and semantic search (retrieval
> without an LLM). Answer generation with Claude comes in step 2.

| Step | What | Status |
|---|---|---|
| 1 | Ingest PDF / Markdown / text → chunk → embed → Postgres + pgvector; search API | ✅ done |
| 2 | RAG answers with Claude, file + section citations, "I don't know" | ⏳ next |
| 3 | Web UI (React + TypeScript + Vite + Tailwind) | |
| 4 | Evaluation set + scoring script, tracked over time | |
| 5 | Docker Compose one-command run, deploy, GIF | |

## Quickstart (step 1)

Requirements: [uv](https://docs.astral.sh/uv/), Docker (Docker Desktop, Colima or OrbStack).

```bash
cp .env.example .env                  # defaults work as-is
docker compose up -d --wait db        # Postgres 16 + pgvector on localhost:5433

cd backend
uv sync --extra local                 # includes sentence-transformers for the local embedder
uv run alembic upgrade head           # create tables + HNSW index

uv run lorvo ingest ../samples        # parse, chunk, embed, store
uv run lorvo search "How do I request a day off?"
```

Example output:

```
ingested  employee-handbook.md  (14 chunks)
ingested  onboarding.md  (7 chunks)
ingested  it-security-policy.pdf  (6 chunks)
ingested  office-faq.txt  (1 chunks)

4 files: 4 ingested, 0 updated, 0 skipped, 0 failed; 28 chunks written

[1] 0.742  employee-handbook.md  (chars 483-971)
    Fernhill Labs Employee Handbook > Time Off > Requesting Leave
    Request vacation in the **PeopleHub** portal under *Time Off > New Request*. Submit
    requests at least **2 weeks in advance** for absences of 3 days or more, ...
```

Run it again and every file is `skipped`. Ingest is idempotent.

### HTTP API

```bash
uv run lorvo serve                    # http://127.0.0.1:8000/docs for interactive docs
```

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/documents` | Upload a file (multipart `file`). Same filename again → replaced, or skipped if unchanged |
| `GET` | `/documents` | List documents with format, size, pages, chunk count |
| `DELETE` | `/documents/{id}` | Delete a document and its chunks |
| `GET` | `/search?q=...&k=5` | Top-k chunks with score, heading path, char offsets, page range |

```bash
curl -F "file=@../samples/office-faq.txt" localhost:8000/documents
curl "localhost:8000/search?q=how+long+is+parental+leave&k=1"
```

## How it works

```
 files ──► parser ──► sections ──► chunker ──► embedder ──► Postgres (pgvector)
           md/pdf/txt  heading path  ~350 tokens  bge-small    documents + chunks
                       + offsets     + header     384-d        HNSW cosine index
                                                                   │
 query ──────────────────────────────────────► embed_query ──► top-k chunks
```

1. **Parse** every format into a common `ParsedDocument`: sections with a heading
   path (`Employee Handbook > Time Off > Requesting Leave`) and char offsets into
   the stored document text. PDF headings are inferred from font size and boldness.
2. **Chunk** structure-first: a section that fits is one chunk; long sections split
   on paragraphs, then sentences, then words, with ~50 tokens of overlap.
3. **Embed** the chunk *with its heading path prefixed*, using
   `BAAI/bge-small-en-v1.5` locally.
4. **Store** documents and chunks (text, heading path, offsets, pages, vector) in
   one Postgres transaction.

## Design decisions

**Postgres + pgvector instead of a dedicated vector DB.** One transactional store
holds documents, chunk metadata and vectors. Re-ingesting a file swaps its chunks
atomically, so there's no second system that can drift out of sync. Postgres
full-text search later enables hybrid (keyword + vector) retrieval in the same
query. At this scale (thousands to low millions of chunks), HNSW in pgvector is
fast enough.

**Structure-first chunking.** Company docs are already organised by headings,
and a section is the unit a human would cite. Splitting on structure before size
keeps chunks coherent and makes citations precise. Small sections are
deliberately *not* merged, because merging would blur which section an answer came from.

**Contextual headers.** A chunk saying *"Submit the form 2 weeks in advance"*
doesn't mention leave. Prefixing `Handbook > Time Off > Requesting Leave` before
embedding lets it match *"how do I request a day off?"*. The header counts toward
the token budget so inputs stay under the model's 512-token limit, and token
counts use the embedder's own tokenizer, not an estimate.

**Offsets into stored text, for every format.** Each chunk's
`content[char_start:char_end]` is exactly its text (an invariant tested for every
parser), and PDFs also record pages. Step 2's click-to-view citations then just
highlight a span, the same way for every file type.

**Idempotent ingest keyed on content *and* pipeline.** A file is skipped only if
its SHA-256 **and** a fingerprint of the embedder + chunker settings are unchanged.
Hashing the file alone would silently keep stale chunks after tuning chunk size
in step 4. Embedding runs before the write transaction opens, so the
transaction stays short.

**Local embeddings, behind a protocol.** bge-small is free, needs no API key,
is deterministic and runs on Apple Silicon (MPS). BGE expects an instruction
prefix on *queries* but not passages, so the protocol has separate
`embed_query` / `embed_documents`. A `FakeEmbedder` (hashed bag-of-words) makes
tests fast and meaningful without downloading a model. It's an optional extra,
so CI never installs torch. Changing to a model with a different dimension is
refused at startup until a migration changes the `vector(384)` column.

## Known limitations (inputs for step 4)

- **Dense-only retrieval misses keyword-heavy queries.** *"What's the guest
  wifi password?"* ranks the security policy's *Passwords* section above the FAQ
  entry that answers it, because the FAQ is a plain-text file with no headings
  and becomes one broad chunk. Hybrid search (Postgres full-text + vectors) and
  finer splitting for unstructured text are planned. The eval set in step 4 will
  measure whether they help.
- Scanned (image-only) PDFs have no extractable text and are reported as failed;
  OCR is out of scope for now.
- Deleting a file from a folder does not yet remove it from the index on re-ingest.

## Development

```bash
cd backend
uv sync --extra local
uv run ruff check && uv run ruff format --check   # lint + format
uv run mypy                                       # strict type checking
uv run pytest                                     # unit + integration tests
uv run pytest -m "not slow"                       # skip the real-model test
```

Integration tests run against real Postgres + pgvector (migrated from scratch on
each run) when `TEST_DATABASE_URL` is set. The `.env.example` value points at the
`lorvo_test` database that docker compose creates. Without it, they're skipped.
CI (GitHub Actions) runs everything against a pgvector service container.

Regenerate the sample PDF with `uv run python scripts/make_sample_pdf.py`.

```
backend/
  src/lorvo/
    config.py              settings from env vars (pydantic-settings)
    db/                    SQLAlchemy models, session helpers
    ingest/parsers/        markdown.py, pdf.py, text.py → ParsedDocument
    ingest/chunker.py      structure-first chunking
    ingest/embedder.py     Embedder protocol: LocalEmbedder, FakeEmbedder
    ingest/pipeline.py     parse → chunk → embed → store
    retrieval/search.py    top-k cosine search
    api/                   FastAPI routes, schemas, dependencies
    main.py, cli.py
  alembic/                 migrations
  tests/unit, tests/integration
samples/                   fictional company docs for demos
```

## Configuration

All settings come from environment variables (or `.env`, which is git-ignored);
see [`.env.example`](.env.example). Secrets are never committed.

| Variable | Default | |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://lorvo:lorvo@localhost:5433/lorvo` | |
| `EMBEDDER` | `local` | `local` or `fake` (tests) |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | |
| `CHUNK_TARGET_TOKENS` / `CHUNK_OVERLAP_TOKENS` | `350` / `50` | |
| `ANTHROPIC_API_KEY` | — | used from step 2 |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | e.g. `claude-opus-5-5` |

## Notes

- Sample documents describe **Fernhill Labs, a fictional company**. No real
  policies or personal data.
- PDF parsing uses [PyMuPDF](https://pymupdf.readthedocs.io/), which is
  AGPL-3.0 licensed. That's fine for an open-source project; a closed-source
  deployment would need a commercial licence or a switch to `pdfplumber`/`pypdf`.

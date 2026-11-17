"""Command-line interface: `lorvo ingest ./samples`."""

from collections import Counter
from pathlib import Path
from typing import Annotated

import typer

from lorvo.config import get_settings
from lorvo.db.session import make_engine, make_session_factory
from lorvo.ingest.chunker import ChunkerConfig
from lorvo.ingest.embedder import build_embedder
from lorvo.ingest.pipeline import IngestPipeline

app = typer.Typer(help="Lorvo: answers about your documents, with citations.", no_args_is_help=True)

_STATUS_COLORS = {
    "ingested": typer.colors.GREEN,
    "updated": typer.colors.CYAN,
    "skipped": typer.colors.BRIGHT_BLACK,
    "failed": typer.colors.RED,
}


def _pipeline() -> IngestPipeline:
    settings = get_settings()
    return IngestPipeline(
        make_session_factory(make_engine(settings.database_url)),
        build_embedder(settings),
        ChunkerConfig(settings.chunk_target_tokens, settings.chunk_overlap_tokens),
    )


@app.callback()
def main() -> None:
    """Lorvo command-line tools."""


@app.command()
def ingest(
    path: Annotated[
        Path, typer.Argument(exists=True, help="A file or a folder of PDF/Markdown/text files.")
    ],
) -> None:
    """Parse, chunk, embed and store documents. Unchanged files are skipped."""
    results = _pipeline().ingest_path(path)
    for r in results:
        detail = f"{r.chunks} chunks" if r.status != "failed" else r.error
        status = typer.style(f"{r.status:>8}", fg=_STATUS_COLORS[r.status])
        typer.echo(f"{status}  {r.filename}  ({detail})")

    counts = Counter(r.status for r in results)
    new_chunks = sum(r.chunks for r in results if r.status in ("ingested", "updated"))
    typer.echo(
        f"\n{len(results)} files: {counts['ingested']} ingested, {counts['updated']} updated, "
        f"{counts['skipped']} skipped, {counts['failed']} failed; {new_chunks} chunks written"
    )
    if counts["failed"]:
        raise typer.Exit(code=1)


@app.command("search")
def search_cmd(
    query: Annotated[str, typer.Argument(help="Natural-language question.")],
    k: Annotated[int, typer.Option("-k", min=1, max=50, help="Number of results.")] = 5,
) -> None:
    """Show the top-k most relevant chunks for a query (retrieval only, no LLM)."""
    from lorvo.retrieval.search import search

    settings = get_settings()
    factory = make_session_factory(make_engine(settings.database_url))
    with factory() as session:
        hits = search(session, build_embedder(settings), query, k)
    if not hits:
        typer.echo("No documents ingested yet. Try: lorvo ingest ../samples")
        return
    for i, h in enumerate(hits, 1):
        where = f"p.{h.page_start}" if h.page_start else f"chars {h.char_start}-{h.char_end}"
        path = " > ".join(h.heading_path) or "(no heading)"
        typer.secho(f"\n[{i}] {h.score:.3f}  {h.filename}  ({where})", bold=True)
        typer.secho(f"    {path}", fg=typer.colors.CYAN)
        snippet = " ".join(h.text.split())
        typer.echo(f"    {snippet[:300]}{'…' if len(snippet) > 300 else ''}")


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: Annotated[bool, typer.Option(help="Auto-reload on code changes.")] = False,
) -> None:
    """Run the HTTP API (docs at /docs)."""
    import uvicorn

    uvicorn.run("lorvo.main:app", host=host, port=port, reload=reload)

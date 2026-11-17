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

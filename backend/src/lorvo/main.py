"""FastAPI application: `uvicorn lorvo.main:app`."""

from fastapi import FastAPI

from lorvo import __version__
from lorvo.api.routes import documents, search


def create_app() -> FastAPI:
    app = FastAPI(
        title="Lorvo",
        version=__version__,
        description="Answers questions about your team's documents, with citations.",
    )
    app.include_router(documents.router)
    app.include_router(search.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

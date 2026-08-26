"""FastAPI application factory.

Follows deer-flow's shape: build everything in create_app(), keep routers thin.
The source adapter is stateless (it only holds the database path), so it is
assembled directly instead of in a lifespan; a lifespan arrives with the first
resource that actually needs setup/teardown.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from zlens import __version__
from zlens.api.routers import health, meta, models, overview, performance, projects, trends
from zlens.core.config import Settings, load_settings
from zlens.sources.base import SourceError, SourceUnavailable
from zlens.sources.zcode import ZcodeSource


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="zlens", version=__version__)
    app.state.settings = settings
    app.state.source = ZcodeSource(settings.db_path)

    @app.exception_handler(SourceError)
    async def source_error_handler(request: Request, exc: SourceError) -> JSONResponse:
        code = "source_unavailable" if isinstance(exc, SourceUnavailable) else "schema_incompatible"
        return JSONResponse(
            status_code=503,
            content={"error": {"code": code, "message": str(exc)}},
        )

    app.include_router(meta.router)
    app.include_router(overview.router)
    app.include_router(trends.router)
    app.include_router(models.router)
    app.include_router(projects.router)
    app.include_router(performance.router)
    app.include_router(health.router)
    return app


app = create_app()

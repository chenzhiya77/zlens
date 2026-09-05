"""FastAPI application factory.

Follows deer-flow's shape: build everything in create_app(), keep routers thin.
The source adapter is stateless (it only holds the database path), so it is
assembled directly instead of in a lifespan; a lifespan arrives with the first
resource that actually needs setup/teardown.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from zlens import __version__
from zlens.api.routers import (
    export,
    health,
    meta,
    models,
    overview,
    performance,
    pricing,
    projects,
    rates,
    trends,
)
from zlens.api.routers import settings as settings_router
from zlens.core.config import Settings, load_settings, with_config_overlay
from zlens.sources.base import SourceError, SourceUnavailable
from zlens.sources.claude import ClaudeSource
from zlens.sources.minimax import MinimaxSource
from zlens.sources.multi import MultiSource
from zlens.sources.opencode import OpencodeSource
from zlens.sources.qoder import QoderSource
from zlens.sources.qoder_cn import QoderCnSource
from zlens.sources.workbuddy import WorkbuddySource
from zlens.sources.zcode import ZcodeSource

# Built by `make build-web` (frontend/ → ../src/zlens/web/static_dist).
_STATIC_DIST = Path(__file__).resolve().parent.parent / "web" / "static_dist"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = with_config_overlay(settings or load_settings())
    app = FastAPI(title="zlens", version=__version__)
    app.state.settings = settings
    app.state.source = MultiSource(
        [
            ZcodeSource(settings.db_path),
            MinimaxSource(settings.minimax_sessions_dir),
            OpencodeSource(settings.opencode_db_path),
            WorkbuddySource(settings.workbuddy_dir),
            QoderCnSource(settings.qoder_cn_config_dir),
            QoderSource(settings.qoder_config_dir),
            ClaudeSource(settings.claude_config_dir),
        ]
    )

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
    app.include_router(pricing.router)
    app.include_router(rates.router)
    app.include_router(settings_router.router)
    app.include_router(export.router)

    if _STATIC_DIST.is_dir():
        # Single-process delivery: API routes above win by registration order,
        # everything else falls through to the built SPA. Client-side routes
        # (e.g. /trends) get index.html via the 404 fallback.
        app.mount("/", StaticFiles(directory=_STATIC_DIST, html=True), name="web")

        @app.exception_handler(StarletteHTTPException)
        async def http_exception(request: Request, exc: StarletteHTTPException):
            is_spa_route = exc.status_code == 404 and not request.url.path.startswith("/api")
            if is_spa_route:
                return FileResponse(_STATIC_DIST / "index.html")
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    return app


app = create_app()

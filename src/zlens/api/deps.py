"""Request-scoped access to singletons assembled by the app factory."""

from datetime import date

from fastapi import HTTPException, Query, Request

from zlens.core.config import Settings
from zlens.sources.models import DateWindow
from zlens.sources.multi import MultiSource


def get_source(request: Request) -> MultiSource:
    return request.app.state.source


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_window(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> DateWindow | None:
    """Closed local-day window for the windowed endpoints; None = 全量.

    Only absolute ISO dates are accepted (malformed strings fail FastAPI's own
    422 parsing); a relative "近 N 天" is the frontend's to translate.
    """
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=422,
            detail=f"invalid date window: start ({start}) is after end ({end})",
        )
    if start is None and end is None:
        return None
    return DateWindow(start=start, end=end)

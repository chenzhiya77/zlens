"""Request-scoped access to singletons assembled by the app factory."""

from datetime import date, datetime

from fastapi import HTTPException, Query, Request

from zlens.core.config import Settings
from zlens.sources.models import DateWindow, SortColumn, SortOrder, TimeWindow
from zlens.sources.multi import MultiSource


def get_source(request: Request) -> MultiSource:
    return request.app.state.source


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_sort(
    sort: SortColumn = Query(default="total_tokens"),
    order: SortOrder = Query(default="desc"),
) -> tuple[SortColumn, SortOrder]:
    """Table sort for the windowed ranking endpoints.

    Defaults preserve today's ordering (total_tokens desc); the unpriced-last
    rule is applied server-side in sort_usage_rows. Literal typing makes FastAPI
    reject unknown columns/orders with a 422 naming the allowed values.
    """
    return sort, order


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


def get_time_window(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
) -> TimeWindow | None:
    """Half-open instant window [since, until) for the runtime-quality endpoints;
    None = 全量.

    Only absolute ISO datetimes are accepted (naive = local time, the app's only
    clock); a relative "近 1 小时" is the frontend's to translate. Half-open, so
    a date-level custom range maps to [day 00:00, day+1 00:00) exactly.
    """
    if since is not None and until is not None and since >= until:
        raise HTTPException(
            status_code=422,
            detail=f"invalid time window: since ({since}) is not before until ({until})",
        )
    if since is None and until is None:
        return None
    return TimeWindow(since=since, until=until)

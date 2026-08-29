from datetime import timedelta

from fastapi import APIRouter, Depends, Query

from zlens.api.deps import get_settings, get_sort, get_source, get_window
from zlens.core.config import Settings
from zlens.core.cost import PriceTable, enrich_overview, metric_delta
from zlens.sources.models import (
    DateWindow,
    Overview,
    PeriodDelta,
    SortColumn,
    SortOrder,
    sort_usage_rows,
)
from zlens.sources.multi import MultiSource

router = APIRouter(prefix="/api", tags=["overview"])


def _period_delta(
    current: Overview, selected: MultiSource, window: DateWindow, table: PriceTable
) -> PeriodDelta | None:
    """环比 vs the previous equal-length window (等长前移, never calendar months).

    Only for closed windows — 「全部」 has no previous to define. The previous
    window must be fully inside the data range AND contain requests; missing
    usage must vanish, not render as "+300%".
    """
    if window.start is None or window.end is None:
        return None
    length = (window.end - window.start).days + 1
    prev_end = window.start - timedelta(days=1)
    prev_start = window.start - timedelta(days=length)
    first = selected.meta().first_request_at
    if first is None or first.astimezone().date() > prev_start:
        return None
    previous = enrich_overview(selected.overview(DateWindow(start=prev_start, end=prev_end)), table)
    if previous.request_count == 0:
        return None
    return PeriodDelta(
        request_count=metric_delta(current.request_count, previous.request_count),
        estimated_cost=metric_delta(current.estimated_cost, previous.estimated_cost),
    )


@router.get("/overview", response_model=Overview)
def get_overview(
    store: MultiSource = Depends(get_source),
    settings: Settings = Depends(get_settings),
    source: str | None = Query(default=None),
    window: DateWindow | None = Depends(get_window),
    sort: tuple[SortColumn, SortOrder] = Depends(get_sort),
) -> Overview:
    table = PriceTable.load(settings.pricing_path)
    selected = store.select(source)
    result = enrich_overview(selected.overview(window), table)
    # Sort after costing: estimated_cost only exists once prices are attached,
    # and the unpriced-last rule is part of the sort, not of the data.
    update: dict = {"by_model": sort_usage_rows(result.by_model, *sort)}
    if window is not None:
        update["delta"] = _period_delta(result, selected, window, table)
    return result.model_copy(update=update)

from fastapi import APIRouter, Depends, Query

from zlens.api.deps import get_settings, get_sort, get_source, get_window
from zlens.core.config import Settings
from zlens.core.cost import PriceTable, enrich_overview
from zlens.sources.models import DateWindow, Overview, SortColumn, SortOrder, sort_usage_rows
from zlens.sources.multi import MultiSource

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=Overview)
def get_overview(
    store: MultiSource = Depends(get_source),
    settings: Settings = Depends(get_settings),
    source: str | None = Query(default=None),
    window: DateWindow | None = Depends(get_window),
    sort: tuple[SortColumn, SortOrder] = Depends(get_sort),
) -> Overview:
    table = PriceTable.load(settings.pricing_path)
    result = enrich_overview(store.select(source).overview(window), table)
    # Sort after costing: estimated_cost only exists once prices are attached,
    # and the unpriced-last rule is part of the sort, not of the data.
    return result.model_copy(update={"by_model": sort_usage_rows(result.by_model, *sort)})

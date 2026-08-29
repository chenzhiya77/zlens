from fastapi import APIRouter, Depends, Query

from zlens.api.deps import get_settings, get_sort, get_source, get_window
from zlens.core.config import Settings
from zlens.core.cost import PriceTable, attach_model_costs
from zlens.sources.models import (
    DateWindow,
    ModelsRanking,
    SortColumn,
    SortOrder,
    sort_usage_rows,
)
from zlens.sources.multi import MultiSource

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models", response_model=ModelsRanking)
def get_models_ranking(
    store: MultiSource = Depends(get_source),
    settings: Settings = Depends(get_settings),
    source: str | None = Query(default=None),
    window: DateWindow | None = Depends(get_window),
    sort: tuple[SortColumn, SortOrder] = Depends(get_sort),
) -> ModelsRanking:
    ranking = store.select(source).models_ranking(window)
    table = PriceTable.load(settings.pricing_path)
    models = attach_model_costs(ranking.models, table)
    return ranking.model_copy(update={"models": sort_usage_rows(models, *sort)})

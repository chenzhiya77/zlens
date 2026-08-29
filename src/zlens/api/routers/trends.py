from fastapi import APIRouter, Depends, Query

from zlens.api.deps import get_settings, get_source, get_window
from zlens.core.config import Settings
from zlens.core.cost import PriceTable, fold_daily
from zlens.sources.models import DailyTrends, DateWindow
from zlens.sources.multi import MultiSource

router = APIRouter(prefix="/api", tags=["trends"])


@router.get("/trends/daily", response_model=DailyTrends)
def get_daily_trends(
    store: MultiSource = Depends(get_source),
    settings: Settings = Depends(get_settings),
    source: str | None = Query(default=None),
    window: DateWindow | None = Depends(get_window),
) -> DailyTrends:
    table = PriceTable.load(settings.pricing_path)
    return fold_daily(store.select(source).daily_by_model(window), table)

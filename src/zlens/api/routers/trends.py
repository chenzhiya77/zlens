from fastapi import APIRouter, Depends

from zlens.api.deps import get_settings, get_source
from zlens.core.config import Settings
from zlens.core.cost import PriceTable, fold_daily
from zlens.sources.base import SourceAdapter
from zlens.sources.models import DailyTrends

router = APIRouter(prefix="/api", tags=["trends"])


@router.get("/trends/daily", response_model=DailyTrends)
def get_daily_trends(
    source: SourceAdapter = Depends(get_source),
    settings: Settings = Depends(get_settings),
) -> DailyTrends:
    return fold_daily(source.daily_by_model(), PriceTable.load(settings.pricing_path))

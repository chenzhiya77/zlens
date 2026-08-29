from fastapi import APIRouter, Depends, Query

from zlens.api.deps import get_settings, get_source, get_window
from zlens.core.config import Settings
from zlens.core.cost import PriceTable, enrich_overview
from zlens.sources.models import DateWindow, Overview
from zlens.sources.multi import MultiSource

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=Overview)
def get_overview(
    store: MultiSource = Depends(get_source),
    settings: Settings = Depends(get_settings),
    source: str | None = Query(default=None),
    window: DateWindow | None = Depends(get_window),
) -> Overview:
    table = PriceTable.load(settings.pricing_path)
    return enrich_overview(store.select(source).overview(window), table)

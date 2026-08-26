from fastapi import APIRouter, Depends

from zlens.api.deps import get_settings, get_source
from zlens.core.config import Settings
from zlens.core.cost import PriceTable, enrich_overview
from zlens.sources.base import SourceAdapter
from zlens.sources.models import Overview

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=Overview)
def get_overview(
    source: SourceAdapter = Depends(get_source),
    settings: Settings = Depends(get_settings),
) -> Overview:
    return enrich_overview(source.overview(), PriceTable.load(settings.pricing_path))

from fastapi import APIRouter, Depends

from zlens.api.deps import get_settings, get_source
from zlens.core.config import Settings
from zlens.core.cost import PriceTable
from zlens.sources.base import SourceAdapter
from zlens.sources.models import MetaInfo

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/meta", response_model=MetaInfo)
def get_meta(
    source: SourceAdapter = Depends(get_source),
    settings: Settings = Depends(get_settings),
) -> MetaInfo:
    table = PriceTable.load(settings.pricing_path)
    unpriced = sorted(set(source.model_ids()) - set(table.models))
    return source.meta().model_copy(update={"unpriced_models": unpriced})

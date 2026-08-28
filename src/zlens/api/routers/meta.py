from fastapi import APIRouter, Depends, Query

from zlens.api.deps import get_settings, get_source
from zlens.core.config import Settings
from zlens.core.cost import PriceTable
from zlens.sources.models import MetaInfo
from zlens.sources.multi import MultiSource

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/meta", response_model=MetaInfo)
def get_meta(
    store: MultiSource = Depends(get_source),
    settings: Settings = Depends(get_settings),
    source: str | None = Query(default=None),
) -> MetaInfo:
    selected = store.select(source)
    table = PriceTable.load(settings.pricing_path)
    unpriced = sorted(set(selected.model_keys()) - set(table.models))
    return selected.meta().model_copy(update={"unpriced_models": unpriced})

from fastapi import APIRouter, Depends, Query

from zlens import __version__
from zlens.api.deps import get_settings, get_source, get_window
from zlens.core.config import Settings
from zlens.core.cost import PriceTable
from zlens.sources.models import DateWindow, MetaInfo
from zlens.sources.multi import MultiSource

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/meta", response_model=MetaInfo)
def get_meta(
    store: MultiSource = Depends(get_source),
    settings: Settings = Depends(get_settings),
    source: str | None = Query(default=None),
    window: DateWindow | None = Depends(get_window),
) -> MetaInfo:
    selected = store.select(source)
    table = PriceTable.load(settings.pricing_path)
    unpriced = sorted(set(selected.model_keys(window)) - set(table.models))
    return selected.meta(window).model_copy(
        update={"unpriced_models": unpriced, "version": __version__}
    )

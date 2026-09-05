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
    meta = selected.meta(window)
    # Credit-side analogue of unpriced_models: a source reporting credits with
    # neither basis priced — the list the pricing page's credit entry nudges
    # the user to fill (token prices do not apply to these sources).
    unpriced_credits = sorted(
        source
        for source in meta.credit_reporting_sources
        if table.credit_price_for(source, "plan") is None
        and table.credit_price_for(source, "pack") is None
    )
    # The enumeration always carries the full registry (even when ?source= picks
    # one): a chip that vanishes because its source died reads as "never existed".
    return meta.model_copy(
        update={
            "unpriced_models": unpriced,
            "unpriced_credits": unpriced_credits,
            "version": __version__,
            "sources": store.source_refs(),
        }
    )

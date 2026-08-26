from fastapi import APIRouter, Depends

from zlens.api.deps import get_settings, get_source
from zlens.core.config import Settings
from zlens.core.cost import PriceTable, attach_model_costs
from zlens.sources.base import SourceAdapter
from zlens.sources.models import ModelsRanking

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models", response_model=ModelsRanking)
def get_models_ranking(
    source: SourceAdapter = Depends(get_source),
    settings: Settings = Depends(get_settings),
) -> ModelsRanking:
    ranking = source.models_ranking()
    table = PriceTable.load(settings.pricing_path)
    return ranking.model_copy(update={"models": attach_model_costs(ranking.models, table)})

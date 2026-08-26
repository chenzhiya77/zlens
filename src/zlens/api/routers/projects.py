from fastapi import APIRouter, Depends, Query

from zlens.api.deps import get_settings, get_source
from zlens.core.config import Settings
from zlens.core.cost import PriceTable, fold_projects
from zlens.sources.models import ProjectsReport
from zlens.sources.multi import MultiSource

router = APIRouter(prefix="/api", tags=["projects"])


@router.get("/projects", response_model=ProjectsReport)
def get_projects(
    store: MultiSource = Depends(get_source),
    settings: Settings = Depends(get_settings),
    source: str | None = Query(default=None),
) -> ProjectsReport:
    table = PriceTable.load(settings.pricing_path)
    return fold_projects(store.select(source).usage_by_project_model(), table)

from fastapi import APIRouter, Depends

from zlens.api.deps import get_settings, get_source
from zlens.core.config import Settings
from zlens.core.cost import PriceTable, fold_projects
from zlens.sources.base import SourceAdapter
from zlens.sources.models import ProjectsReport

router = APIRouter(prefix="/api", tags=["projects"])


@router.get("/projects", response_model=ProjectsReport)
def get_projects(
    source: SourceAdapter = Depends(get_source),
    settings: Settings = Depends(get_settings),
) -> ProjectsReport:
    return fold_projects(source.usage_by_project_model(), PriceTable.load(settings.pricing_path))

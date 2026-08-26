from fastapi import APIRouter, Depends

from zlens.api.deps import get_source
from zlens.sources.base import SourceAdapter
from zlens.sources.models import HealthReport

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthReport)
def get_health(source: SourceAdapter = Depends(get_source)) -> HealthReport:
    return source.health_summary()

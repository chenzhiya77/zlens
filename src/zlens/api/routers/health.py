from fastapi import APIRouter, Depends, Query

from zlens.api.deps import get_source
from zlens.sources.models import HealthReport
from zlens.sources.multi import MultiSource

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthReport)
def get_health(
    store: MultiSource = Depends(get_source),
    source: str | None = Query(default=None),
) -> HealthReport:
    return store.select(source).health_summary()

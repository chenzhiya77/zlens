from fastapi import APIRouter, Depends, Query

from zlens.api.deps import get_source, get_time_window
from zlens.sources.models import HealthReport, TimeWindow
from zlens.sources.multi import MultiSource

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthReport)
def get_health(
    store: MultiSource = Depends(get_source),
    source: str | None = Query(default=None),
    window: TimeWindow | None = Depends(get_time_window),
) -> HealthReport:
    return store.select(source).health_summary(window)

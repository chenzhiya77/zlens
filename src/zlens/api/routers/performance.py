from fastapi import APIRouter, Depends, Query

from zlens.api.deps import get_source
from zlens.core.stats import latency_stats
from zlens.sources.models import PerformanceReport
from zlens.sources.multi import MultiSource

router = APIRouter(prefix="/api", tags=["performance"])


@router.get("/performance", response_model=PerformanceReport)
def get_performance(
    store: MultiSource = Depends(get_source),
    source: str | None = Query(default=None),
) -> PerformanceReport:
    durations, ttfts = store.select(source).latency_samples()
    return PerformanceReport(
        duration_ms=latency_stats(durations),
        time_to_first_token_ms=latency_stats(ttfts),
    )

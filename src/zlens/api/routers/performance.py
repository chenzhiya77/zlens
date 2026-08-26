from fastapi import APIRouter, Depends

from zlens.api.deps import get_source
from zlens.core.stats import latency_stats
from zlens.sources.base import SourceAdapter
from zlens.sources.models import PerformanceReport

router = APIRouter(prefix="/api", tags=["performance"])


@router.get("/performance", response_model=PerformanceReport)
def get_performance(source: SourceAdapter = Depends(get_source)) -> PerformanceReport:
    durations, ttfts = source.latency_samples()
    return PerformanceReport(
        duration_ms=latency_stats(durations),
        time_to_first_token_ms=latency_stats(ttfts),
    )

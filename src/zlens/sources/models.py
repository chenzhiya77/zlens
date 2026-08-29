"""Data contracts produced by source adapters and served by the API.

Row-level models carry `source` so multi-source merges stay attributable
(see docs/specs/v2-multi-source-spec.md).

Token buckets are mutually exclusive by contract: `input_tokens` counts only the
prompt tokens that were *not* served from cache, `output_tokens` counts everything
billed at the output price (reasoning included, hence `reasoning_tokens` is a
breakdown of it, never an extra bucket), and `cache_creation_tokens` /
`cache_read_tokens` are their own priced tiers. The four sum to `total_tokens`.
Costing multiplies each bucket by its own unit price, so a source that reports the
cached prefix *inside* its input must subtract it in its adapter — leaving it
nested charges those tokens twice, at the full input price.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


def model_key(source: str, provider_id: str, model_id: str) -> str:
    """Canonical channel identity: 'source|provider_id|model_id'.

    The price table and display aliases both address a channel by this key, so
    the same model id served through two channels never shares one price.
    """
    return f"{source}|{provider_id}|{model_id}"


@dataclass(frozen=True, slots=True)
class DateWindow:
    """Closed local-day window [start, end]; a None bound is unbounded.

    The API accepts only absolute ISO dates — a relative expression like "近 7 天"
    is the frontend's to translate, because its anchor (today vs the last request)
    is a product decision, not an API guess. Default (no window) means the full
    history, so "全部" needs no special branch anywhere downstream.
    """

    start: date | None = None
    end: date | None = None

    def contains_day(self, day: str) -> bool:
        """Membership for a 'YYYY-MM-DD' local-day string as produced by the
        adapters' day cut (SQL date(...) or ms_to_local_day)."""
        return (self.start is None or day >= self.start.isoformat()) and (
            self.end is None or day <= self.end.isoformat()
        )


class ModelUsageSummary(BaseModel):
    source: str = "zcode"
    provider_id: str
    model_id: str
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost: float | None = None
    # cache_read / (input + cache_read + cache_creation): share of the prompt
    # tokens served from cache. Denominator 0 -> None (not 0%, not 100%).
    cache_hit_rate: float | None = None


SortColumn = Literal["total_tokens", "estimated_cost", "request_count"]
SortOrder = Literal["desc", "asc"]


def sort_usage_rows(
    rows: list["ModelUsageSummary"], sort: SortColumn, order: SortOrder
) -> list["ModelUsageSummary"]:
    """Backend-side table sort (T19): the unpriced-last rule lives here, server
    side, so no client re-sort can ever mix "unknown cost" into the middle of a
    cost ranking where it would read as "cheap" instead of "unpriced".
    """
    reverse = order == "desc"
    if sort == "estimated_cost":
        priced = sorted(
            (r for r in rows if r.estimated_cost is not None),
            key=lambda r: r.estimated_cost,
            reverse=reverse,
        )
        return priced + [r for r in rows if r.estimated_cost is None]
    key: Callable[[ModelUsageSummary], object] = (
        (lambda r: r.total_tokens) if sort == "total_tokens" else (lambda r: r.request_count)
    )
    return sorted(rows, key=key, reverse=reverse)


class OverviewTotals(BaseModel):
    """Window+source-filtered grand totals for the table footer row (T20).

    Backend-computed, never re-summed in the client: the unpriced rule is a
    business decision, not arithmetic. Token buckets are upstream facts and sum
    unconditionally; the cost total stays null while any served model is unpriced
    (a partial total would silently understate spend). No pagination exists, and
    this is the FULL total by construction — name and shape stay "totals", not
    "page totals", so a future pager cannot bury a semantic trap here.
    """

    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost: float | None = None


class MetricDelta(BaseModel):
    """One metric's period-over-period figure.

    `previous` ships whenever the previous period was measured at all;
    `change_rate` additionally needs both sides present and a non-zero base —
    null means "cannot say", never "no change".
    """

    previous: float | None = None
    change_rate: float | None = None


class PeriodDelta(BaseModel):
    """环比 against the previous equal-length window (等长前移, not calendar months)."""

    request_count: MetricDelta
    estimated_cost: MetricDelta


class Overview(BaseModel):
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost: float | None = None
    # One-off buyout/plan spend from the price table. Filled by the cost layer, not
    # by adapters: it is what was paid, independent of how much was consumed, so it
    # never joins `estimated_cost` and is never gated by the unpriced-model rule.
    # Null means the price table has no buyout row at all — "never filled" must stay
    # distinguishable from a deliberate ¥0 purchase (AGENTS.md: 没填≠0).
    buyout_total: float | None = None
    # cache_read / (input + cache_read + cache_creation) over the merged totals;
    # the denominator is all prompt tokens (方案 A, 分母含缓存写). 0 -> None.
    cache_hit_rate: float | None = None
    # 环比 vs the previous equal-length window. Null unless a closed window is
    # given AND the previous window is fully inside the data range AND non-empty —
    # a missing previous period must vanish, not render as "+300%".
    delta: PeriodDelta | None = None
    totals: OverviewTotals | None = None
    by_model: list[ModelUsageSummary]


class SourceRef(BaseModel):
    """One registered source in the UI enumeration — including the broken ones.

    A dead source must stay visible (greyed out with its reason), not vanish:
    a missing entry reads as "never had any usage", which is a lie.
    """

    id: str
    available: bool
    error: str | None = None


class MetaInfo(BaseModel):
    source_id: str
    # Package version (zlens.__version__) so the SPA footer never hardcodes one.
    # Not source data: adapters leave it empty; the API layer stamps the real value.
    version: str = ""
    # All registered sources with their availability, stamped by the API layer the
    # same way (adapters cannot see the registry). Empty from adapters.
    sources: list[SourceRef] = []
    request_count: int
    first_request_at: datetime | None
    last_request_at: datetime | None
    generated_at: datetime
    # Channel keys (see model_key) that have no price entry yet.
    unpriced_models: list[str] = []


class DailyUsage(BaseModel):
    source: str
    day: str
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost: float | None = None


class DailyModelUsage(BaseModel):
    source: str
    day: str
    provider_id: str
    model_id: str
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost: float | None = None


class DailyTrends(BaseModel):
    granularity: str = "day"  # echoed back so the client can confirm the bucket key
    days: list[DailyUsage]
    by_model: list[DailyModelUsage]


class ModelsRanking(BaseModel):
    models: list[ModelUsageSummary]


class ProjectModelUsage(BaseModel):
    source: str
    directory: str
    title: str
    provider_id: str
    model_id: str
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost: float | None = None


class ProjectUsage(BaseModel):
    source: str
    directory: str
    title: str
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost: float | None = None


class ProjectsReport(BaseModel):
    projects: list[ProjectUsage]


class LatencyStats(BaseModel):
    sample_count: int
    p50_ms: float
    p90_ms: float
    p99_ms: float


class PerformanceReport(BaseModel):
    # None means the column had no non-null samples on this database.
    duration_ms: LatencyStats | None
    time_to_first_token_ms: LatencyStats | None


class ErrorGroup(BaseModel):
    source: str
    error_type: str
    error_code: str | None
    request_count: int


class HealthReport(BaseModel):
    request_count: int
    requests_with_retries: int
    total_retries: int
    cancelled_by_user: int
    context_exceeded: int
    errored_requests: int
    errors: list[ErrorGroup]

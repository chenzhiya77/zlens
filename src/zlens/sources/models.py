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

from datetime import datetime

from pydantic import BaseModel


def model_key(source: str, provider_id: str, model_id: str) -> str:
    """Canonical channel identity: 'source|provider_id|model_id'.

    The price table and display aliases both address a channel by this key, so
    the same model id served through two channels never shares one price.
    """
    return f"{source}|{provider_id}|{model_id}"


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
    buyout_total: float = 0.0
    by_model: list[ModelUsageSummary]


class MetaInfo(BaseModel):
    source_id: str
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

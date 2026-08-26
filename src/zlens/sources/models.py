"""Data contracts produced by source adapters and served by the API."""

from datetime import datetime

from pydantic import BaseModel


class ModelUsageSummary(BaseModel):
    provider_id: str
    model_id: str
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None = None


class Overview(BaseModel):
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None = None
    by_model: list[ModelUsageSummary]


class DailyUsage(BaseModel):
    day: str
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None = None


class DailyModelUsage(BaseModel):
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
    estimated_cost_usd: float | None = None


class DailyTrends(BaseModel):
    days: list[DailyUsage]
    by_model: list[DailyModelUsage]


class ModelsRanking(BaseModel):
    models: list[ModelUsageSummary]


class ProjectModelUsage(BaseModel):
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
    estimated_cost_usd: float | None = None


class ProjectUsage(BaseModel):
    directory: str
    title: str
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None = None


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


class MetaInfo(BaseModel):
    source_id: str
    request_count: int
    first_request_at: datetime | None
    last_request_at: datetime | None
    generated_at: datetime
    unpriced_models: list[str] = []

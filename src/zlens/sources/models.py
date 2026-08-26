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


class MetaInfo(BaseModel):
    source_id: str
    request_count: int
    first_request_at: datetime | None
    last_request_at: datetime | None
    generated_at: datetime
    unpriced_models: list[str] = []

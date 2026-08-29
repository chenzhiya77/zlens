"""Source adapter contract.

v1 ships a single adapter (ZCode). This protocol is the seam where future agent
sources plug in without touching the API layer (see docs/specs/v1-spec.md).
"""

from typing import Protocol

from zlens.sources.models import (
    DailyModelUsage,
    DateWindow,
    HealthReport,
    MetaInfo,
    ModelsRanking,
    Overview,
    ProjectModelUsage,
)


class SourceError(Exception):
    """Base class: the local data source cannot serve a query."""


class SourceUnavailable(SourceError):
    """The source database does not exist or cannot be opened."""


class SchemaIncompatible(SourceError):
    """The source exists but lacks tables/columns this version queries."""


class SourceAdapter(Protocol):
    id: str

    def is_available(self) -> bool: ...

    def model_ids(self) -> list[str]: ...

    def model_keys(self, window: DateWindow | None = None) -> list[str]:
        """Per-channel keys 'source|provider_id|model_id' (price-table granularity)."""
        ...

    def meta(self, window: DateWindow | None = None) -> MetaInfo: ...

    def overview(self, window: DateWindow | None = None) -> Overview: ...

    def daily_by_model(self, window: DateWindow | None = None) -> list[DailyModelUsage]: ...

    def models_ranking(self, window: DateWindow | None = None) -> ModelsRanking: ...

    def usage_by_project_model(self) -> list[ProjectModelUsage]: ...

    def latency_samples(self) -> tuple[list[int], list[int]]: ...

    def health_summary(self) -> HealthReport: ...

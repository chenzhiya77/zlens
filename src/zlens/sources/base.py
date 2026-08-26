"""Source adapter contract.

v1 ships a single adapter (ZCode). This protocol is the seam where future agent
sources plug in without touching the API layer (see docs/specs/v1-spec.md).
"""

from typing import Protocol

from zlens.sources.models import DailyModelUsage, MetaInfo, ModelsRanking, Overview


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

    def meta(self) -> MetaInfo: ...

    def overview(self) -> Overview: ...

    def daily_by_model(self) -> list[DailyModelUsage]: ...

    def models_ranking(self) -> ModelsRanking: ...

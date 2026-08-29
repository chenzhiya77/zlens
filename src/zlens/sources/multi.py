"""Composite source: merge every available adapter into unified views.

Totals sum across sources; detail rows concatenate with their `source` tag.
Adapters are probed once at construction; availability failures are retained
so a lone broken source still degrades to its specific error (e.g.
schema_incompatible) instead of a generic unavailable.
"""

from datetime import datetime

from zlens.sources.base import SchemaIncompatible, SourceAdapter, SourceError, SourceUnavailable
from zlens.sources.models import (
    DailyModelUsage,
    DateWindow,
    HealthReport,
    MetaInfo,
    ModelsRanking,
    Overview,
    ProjectModelUsage,
)


class MultiSource:
    def __init__(self, adapters: list[SourceAdapter]) -> None:
        self._active: list[SourceAdapter] = []
        self._errors: list[SourceError] = []
        for adapter in adapters:
            try:
                if adapter.is_available():
                    self._active.append(adapter)
            except SourceError as exc:
                self._errors.append(exc)

    @property
    def source_ids(self) -> list[str]:
        return [adapter.id for adapter in self._active]

    def select(self, source_id: str | None) -> "MultiSource":
        """Restrict to one source id (None = all). Unknown ids fail loudly."""
        if source_id is None:
            return self
        matches = [a for a in self._active if a.id == source_id]
        if not matches:
            raise SourceUnavailable(f"unknown or unavailable source: {source_id}")
        selected = object.__new__(MultiSource)
        selected._active = matches
        selected._errors = []
        return selected

    def _active_or_raise(self) -> list[SourceAdapter]:
        if self._active:
            return self._active
        schema_errors = [e for e in self._errors if isinstance(e, SchemaIncompatible)]
        if schema_errors:
            raise schema_errors[0]
        if self._errors:
            raise self._errors[0]
        raise SourceUnavailable("no data source configured")

    def is_available(self) -> bool:
        return bool(self._active)

    def model_ids(self) -> list[str]:
        ids: set[str] = set()
        for adapter in self._active_or_raise():
            ids.update(adapter.model_ids())
        return sorted(ids)

    def model_keys(self, window: DateWindow | None = None) -> list[str]:
        keys: set[str] = set()
        for adapter in self._active_or_raise():
            keys.update(adapter.model_keys(window))
        return sorted(keys)

    def meta(self, window: DateWindow | None = None) -> MetaInfo:
        metas = [a.meta(window) for a in self._active_or_raise()]
        firsts = [m.first_request_at for m in metas if m.first_request_at is not None]
        lasts = [m.last_request_at for m in metas if m.last_request_at is not None]
        return MetaInfo(
            source_id="+".join(m.source_id for m in metas),
            request_count=sum(m.request_count for m in metas),
            first_request_at=min(firsts) if firsts else None,
            last_request_at=max(lasts) if lasts else None,
            generated_at=datetime.now().astimezone(),
        )

    def overview(self, window: DateWindow | None = None) -> Overview:
        parts = [a.overview(window) for a in self._active_or_raise()]
        return Overview(
            request_count=sum(p.request_count for p in parts),
            input_tokens=sum(p.input_tokens for p in parts),
            output_tokens=sum(p.output_tokens for p in parts),
            reasoning_tokens=sum(p.reasoning_tokens for p in parts),
            cache_creation_tokens=sum(p.cache_creation_tokens for p in parts),
            cache_read_tokens=sum(p.cache_read_tokens for p in parts),
            total_tokens=sum(p.total_tokens for p in parts),
            by_model=sorted(
                (row for p in parts for row in p.by_model),
                key=lambda m: m.total_tokens,
                reverse=True,
            ),
        )

    def daily_by_model(self, window: DateWindow | None = None) -> list[DailyModelUsage]:
        rows = [row for a in self._active_or_raise() for row in a.daily_by_model(window)]
        return sorted(rows, key=lambda r: (r.day, -r.total_tokens))

    def models_ranking(self, window: DateWindow | None = None) -> ModelsRanking:
        models = [row for a in self._active_or_raise() for row in a.models_ranking(window).models]
        return ModelsRanking(models=sorted(models, key=lambda m: m.total_tokens, reverse=True))

    def usage_by_project_model(self) -> list[ProjectModelUsage]:
        rows = [row for a in self._active_or_raise() for row in a.usage_by_project_model()]
        return sorted(rows, key=lambda p: (p.directory, -p.total_tokens))

    def latency_samples(self) -> tuple[list[int], list[int]]:
        durations: list[int] = []
        ttfts: list[int] = []
        for adapter in self._active_or_raise():
            d, t = adapter.latency_samples()
            durations.extend(d)
            ttfts.extend(t)
        return sorted(durations), sorted(ttfts)

    def health_summary(self) -> HealthReport:
        parts = [a.health_summary() for a in self._active_or_raise()]
        errors = [e for p in parts for e in p.errors]
        return HealthReport(
            request_count=sum(p.request_count for p in parts),
            requests_with_retries=sum(p.requests_with_retries for p in parts),
            total_retries=sum(p.total_retries for p in parts),
            cancelled_by_user=sum(p.cancelled_by_user for p in parts),
            context_exceeded=sum(p.context_exceeded for p in parts),
            errored_requests=sum(p.errored_requests for p in parts),
            errors=sorted(errors, key=lambda e: (-e.request_count, e.error_type)),
        )

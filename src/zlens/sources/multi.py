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
    SourceRef,
    TimeWindow,
)


class MultiSource:
    def __init__(self, adapters: list[SourceAdapter]) -> None:
        self._registered: list[SourceAdapter] = list(adapters)
        self._active: list[SourceAdapter] = []
        self._probe_errors: dict[str, SourceError] = {}
        for adapter in adapters:
            try:
                if adapter.is_available():
                    self._active.append(adapter)
            except SourceError as exc:
                self._probe_errors[adapter.id] = exc

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
        selected._registered = self._registered
        selected._active = matches
        selected._probe_errors = self._probe_errors
        return selected

    def source_refs(self) -> list[SourceRef]:
        """Every registered source with its availability — the UI enumeration.

        Registered, not merely active: a source that failed its probe keeps its
        slot (with the reason) so the UI can grey it out instead of erasing it.
        """
        refs = []
        for adapter in self._registered:
            error = self._probe_errors.get(adapter.id)
            refs.append(
                SourceRef(
                    id=adapter.id,
                    available=error is None and any(a is adapter for a in self._active),
                    error=str(error) if error else None,
                )
            )
        return refs

    def _active_or_raise(self) -> list[SourceAdapter]:
        if self._active:
            return self._active
        schema_errors = [
            e for e in self._probe_errors.values() if isinstance(e, SchemaIncompatible)
        ]
        if schema_errors:
            raise schema_errors[0]
        if self._probe_errors:
            raise next(iter(self._probe_errors.values()))
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
            # Adapter-declared traits, unioned: which selected sources report
            # credits / tokens at all (an empty union = none does).
            credit_reporting_sources=sorted({s for m in metas for s in m.credit_reporting_sources}),
            token_reporting_sources=sorted({s for m in metas for s in m.token_reporting_sources}),
            # Retention caveats ride along from whichever selected source has one.
            retention_hint=("; ".join(hint for m in metas if (hint := m.retention_hint)) or None),
        )

    def overview(self, window: DateWindow | None = None) -> Overview:
        parts = [a.overview(window) for a in self._active_or_raise()]
        # Credits merge by "ignore-null sum": a source not reporting credits has
        # no such ledger (ZCode), it is not missing data — so its absence never
        # poisons the total, and the reporting sources ride along so the UI can
        # scope the number ("仅含 N 个上报积分的来源"). Token totals stay plain
        # sums, but tokens_reported flips to False when any contributing row
        # came from a non-token-reporting source: that total is then partial by
        # construction and must be labeled as such, never silently added.
        rows = [row for p in parts for row in p.by_model]
        credit_rows = [row for row in rows if row.credits is not None]
        original_rows = [row for row in credit_rows if row.original_credits is not None]
        return Overview(
            request_count=sum(p.request_count for p in parts),
            input_tokens=sum(p.input_tokens for p in parts),
            output_tokens=sum(p.output_tokens for p in parts),
            reasoning_tokens=sum(p.reasoning_tokens for p in parts),
            cache_creation_tokens=sum(p.cache_creation_tokens for p in parts),
            cache_read_tokens=sum(p.cache_read_tokens for p in parts),
            total_tokens=sum(p.total_tokens for p in parts),
            credits=(round(sum(row.credits for row in credit_rows), 6) if credit_rows else None),
            original_credits=(
                round(sum(row.original_credits for row in original_rows), 6)
                if original_rows
                else None
            ),
            tokens_reported=all(row.tokens_reported for row in rows),
            credits_reported=any(row.credits_reported for row in rows),
            credit_reporting_sources=sorted({row.source for row in rows if row.credits_reported}),
            token_reporting_sources=sorted({row.source for row in rows if row.tokens_reported}),
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

    def latency_samples(self, window: TimeWindow | None = None) -> tuple[list[int], list[int]]:
        durations: list[int] = []
        ttfts: list[int] = []
        for adapter in self._active_or_raise():
            d, t = adapter.latency_samples(window)
            durations.extend(d)
            ttfts.extend(t)
        return sorted(durations), sorted(ttfts)

    def health_summary(self, window: TimeWindow | None = None) -> HealthReport:
        parts = [a.health_summary(window) for a in self._active_or_raise()]
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

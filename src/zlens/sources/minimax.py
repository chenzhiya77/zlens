"""Read-only adapter over MiniMax Code's session ledger files.

Session directories live under ~/.minimax/v2/sessions/YYYY/MM/DD/<ts-session>/
and hold an append-only ledger.jsonl event stream. Events carrying
messages[].usage are model requests; the model name comes from the sibling
display.jsonl. Fields absent upstream (reasoning tokens, latency, health)
stay zero/empty rather than fabricated.
"""

import json
from datetime import datetime
from pathlib import Path

from zlens.sources.base import SourceUnavailable
from zlens.sources.models import (
    DailyModelUsage,
    DateWindow,
    HealthReport,
    MetaInfo,
    ModelsRanking,
    ModelUsageSummary,
    Overview,
    ProjectModelUsage,
    TimeWindow,
    model_key,
)
from zlens.sources.timeutil import ms_to_datetime, ms_to_local_day


class _UsageRecord:
    __slots__ = (
        "started_at",
        "model_id",
        "workspace",
        "input",
        "output",
        "cache_write",
        "cache_read",
        "total",
    )

    def __init__(
        self,
        started_at: int,
        model_id: str,
        workspace: str | None,
        input: int,
        output: int,
        cache_write: int,
        cache_read: int,
        total: int,
    ) -> None:
        self.started_at = started_at
        self.model_id = model_id
        self.workspace = workspace
        self.input = input
        self.output = output
        self.cache_write = cache_write
        self.cache_read = cache_read
        self.total = total


class MinimaxSource:
    id = "minimax"

    def __init__(self, sessions_dir: Path) -> None:
        self._sessions_dir = sessions_dir

    def is_available(self) -> bool:
        self._session_dirs()
        return True

    def _session_dirs(self) -> list[Path]:
        if not self._sessions_dir.is_dir():
            raise SourceUnavailable(f"MiniMax sessions directory not found: {self._sessions_dir}")
        return sorted(p.parent for p in self._sessions_dir.glob("*/*/*/*/ledger.jsonl"))

    def _records(self, window: DateWindow | None = None) -> list[_UsageRecord]:
        records: list[_UsageRecord] = []
        for session_dir in self._session_dirs():
            model = self._model_of(session_dir)
            workspace: str | None = None
            ledger = session_dir / "ledger.jsonl"
            for line in ledger.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a damaged line must not sink the whole source
                record = event.get("record") or {}
                if workspace is None and record.get("workspaceDir"):
                    workspace = record["workspaceDir"]
                created_ms = event.get("createdAtMs")
                if created_ms is None:
                    continue
                for message in event.get("messages") or []:
                    usage = message.get("usage")
                    if not usage:
                        continue
                    if window is not None and not window.contains_day(ms_to_local_day(created_ms)):
                        continue  # load-level pushdown: the ledger files have no query layer
                    records.append(
                        _UsageRecord(
                            started_at=created_ms,
                            model_id=message.get("model") or model,
                            workspace=workspace,
                            input=usage.get("input", 0),
                            output=usage.get("output", 0),
                            cache_write=usage.get("cacheWrite", 0),
                            cache_read=usage.get("cacheRead", 0),
                            total=usage.get("totalTokens", 0),
                        )
                    )
        return records

    def _model_of(self, session_dir: Path) -> str:
        display = session_dir / "display.jsonl"
        if not display.exists():
            return "unknown"
        for line in reversed(display.read_text(encoding="utf-8").splitlines()):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("model"):
                return payload["model"]
        return "unknown"

    def model_ids(self) -> list[str]:
        return sorted({r.model_id for r in self._records()})

    def model_keys(self, window: DateWindow | None = None) -> list[str]:
        return sorted({model_key(self.id, self.id, r.model_id) for r in self._records(window)})

    def meta(self, window: DateWindow | None = None) -> MetaInfo:
        records = self._records(window)
        stamps = [r.started_at for r in records]
        return MetaInfo(
            source_id=self.id,
            request_count=len(records),
            first_request_at=ms_to_datetime(min(stamps)) if stamps else None,
            last_request_at=ms_to_datetime(max(stamps)) if stamps else None,
            generated_at=datetime.now().astimezone(),
            token_reporting_sources=[self.id],
        )

    def overview(self, window: DateWindow | None = None) -> Overview:
        records = self._records(window)
        by_model: dict[str, ModelUsageSummary] = {}
        for r in records:
            row = by_model.setdefault(
                r.model_id,
                ModelUsageSummary(
                    source=self.id,
                    provider_id=self.id,
                    model_id=r.model_id,
                    request_count=0,
                    input_tokens=0,
                    output_tokens=0,
                    reasoning_tokens=0,
                    cache_creation_tokens=0,
                    cache_read_tokens=0,
                    total_tokens=0,
                ),
            )
            row.request_count += 1
            row.input_tokens += r.input
            row.output_tokens += r.output
            row.cache_creation_tokens += r.cache_write
            row.cache_read_tokens += r.cache_read
            row.total_tokens += r.total
        ranked = sorted(by_model.values(), key=lambda m: m.total_tokens, reverse=True)
        totals = {
            "request_count": len(records),
            "input_tokens": sum(m.input_tokens for m in ranked),
            "output_tokens": sum(m.output_tokens for m in ranked),
            "reasoning_tokens": 0,
            "cache_creation_tokens": sum(m.cache_creation_tokens for m in ranked),
            "cache_read_tokens": sum(m.cache_read_tokens for m in ranked),
            "total_tokens": sum(m.total_tokens for m in ranked),
        }
        return Overview(**totals, by_model=ranked)

    def daily_by_model(self, window: DateWindow | None = None) -> list[DailyModelUsage]:
        acc: dict[tuple[str, str], DailyModelUsage] = {}
        for r in self._records(window):
            day = ms_to_local_day(r.started_at)
            key = (day, r.model_id)
            row = acc.setdefault(
                key,
                DailyModelUsage(
                    source=self.id,
                    day=day,
                    provider_id=self.id,
                    model_id=r.model_id,
                    request_count=0,
                    input_tokens=0,
                    output_tokens=0,
                    reasoning_tokens=0,
                    cache_creation_tokens=0,
                    cache_read_tokens=0,
                    total_tokens=0,
                ),
            )
            row.request_count += 1
            row.input_tokens += r.input
            row.output_tokens += r.output
            row.cache_creation_tokens += r.cache_write
            row.cache_read_tokens += r.cache_read
            row.total_tokens += r.total
        return sorted(acc.values(), key=lambda m: (m.day, -m.total_tokens))

    def models_ranking(self, window: DateWindow | None = None) -> ModelsRanking:
        return ModelsRanking(models=list(self.overview(window).by_model))

    def usage_by_project_model(self) -> list[ProjectModelUsage]:
        acc: dict[tuple[str, str], ProjectModelUsage] = {}
        for r in self._records():
            directory = r.workspace or "(unknown)"
            key = (directory, r.model_id)
            row = acc.setdefault(
                key,
                ProjectModelUsage(
                    source=self.id,
                    directory=directory,
                    title=Path(directory).name or "(untitled)",
                    provider_id=self.id,
                    model_id=r.model_id,
                    request_count=0,
                    input_tokens=0,
                    output_tokens=0,
                    reasoning_tokens=0,
                    cache_creation_tokens=0,
                    cache_read_tokens=0,
                    total_tokens=0,
                ),
            )
            row.request_count += 1
            row.input_tokens += r.input
            row.output_tokens += r.output
            row.cache_creation_tokens += r.cache_write
            row.cache_read_tokens += r.cache_read
            row.total_tokens += r.total
        return sorted(acc.values(), key=lambda p: (p.directory, -p.total_tokens))

    def latency_samples(self, window: TimeWindow | None = None) -> tuple[list[int], list[int]]:
        return [], []  # upstream has no latency fields

    def health_summary(self, window: TimeWindow | None = None) -> HealthReport:
        records = self._records()
        if window is not None:
            # Ledger rows load in bulk (T15), so the instant window prunes here —
            # request_count is the only field minimax can window at all.
            records = [r for r in records if window.contains_ms(r.started_at)]
        return HealthReport(
            request_count=len(records),
            requests_with_retries=0,
            total_retries=0,
            cancelled_by_user=0,
            context_exceeded=0,
            errored_requests=0,
            errors=[],
        )

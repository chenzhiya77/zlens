"""Read-only adapter over Claude Code's local transcripts (T38).

Claude Code writes the transcript family the Qoder CLIs were derived from:
``~/.claude/projects/<escaped-cwd>/<sessionId>.jsonl`` plus per-session
``subagents/agent-*.jsonl``. Metering is plain token tiers — four mutually
exclusive buckets (``input_tokens`` excludes cache; verified on real data:
input 2.31M < cache_read 12M), no upstream total field, no credits — so rows
go straight into the token pipeline and the money side is the ordinary pricing
table.

The one real trap is streaming dedup: one API response is logged as SEVERAL
assistant events sharing one ``message.id`` — either byte-identical replays or
zero-placeholder events followed by the one carrying real usage. Rule (verified
on real data: 549 usage rows → 205 billed calls; naive summation inflates 2.1×):
group by message.id and keep the record with the largest four-tier sum; an
all-zero group is a placeholder and bills nothing. ``.last-cleanup`` marks the
official retention window — surfaced as a meta hint like Qoder CN.
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
from zlens.sources.timeutil import iso_to_epoch_ms, ms_to_datetime, ms_to_local_day

_RETENTION_HINT = "Claude Code 会话本地按 cleanupPeriodDays 保留(默认 30 天),更早的历史已不在本地。"


class _UsageRecord:
    __slots__ = (
        "started_at",
        "cwd",
        "model_id",
        "input",
        "output",
        "reasoning",
        "cache_write",
        "cache_read",
        "total",
    )

    def __init__(
        self,
        started_at: int,
        cwd: str,
        model_id: str,
        input: int,
        output: int,
        reasoning: int,
        cache_write: int,
        cache_read: int,
    ) -> None:
        self.started_at = started_at
        self.cwd = cwd
        self.model_id = model_id
        self.input = input
        self.output = output
        self.reasoning = reasoning
        self.cache_write = cache_write
        self.cache_read = cache_read
        # 上游无 total 字段:契约 total = 四档相加(四档实测互斥)。
        self.total = input + output + cache_write + cache_read


def _sum_of(record: _UsageRecord) -> int:
    return record.total


class ClaudeSource:
    id = "claude"

    def __init__(self, config_dir: Path) -> None:
        self._config_dir = config_dir

    def is_available(self) -> bool:
        self._transcripts()
        return True

    def _transcripts(self) -> list[Path]:
        projects = self._config_dir / "projects"
        if not projects.is_dir():
            raise SourceUnavailable(f"Claude Code projects directory not found: {projects}")
        return sorted(projects.rglob("*.jsonl"))

    def _records(self, window: DateWindow | None = None) -> list[_UsageRecord]:
        # 流式去重:message.id 同组的多种事件形态(逐位重放 / 全零占位 + 真用量)
        # 都归约为四档合计最大的一条;全零占位行在解析期就被跳过。重放副本的
        # timestamp 逐位相同,所以先全局去重、后按窗口过滤不会有跨窗歧义。
        best: dict[str, _UsageRecord] = {}
        extras: list[_UsageRecord] = []
        for path in self._transcripts():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a damaged line must not sink the whole source
                if event.get("type") not in ("assistant", "message"):
                    continue
                if (event.get("message") or {}).get("role") != "assistant":
                    continue
                message = event.get("message") or {}
                usage = message.get("usage")
                if not isinstance(usage, dict) or not usage:
                    continue
                model_id = message.get("model")
                if not model_id or model_id == "<synthetic>":
                    continue  # synthetic error records are not model calls
                stamp = iso_to_epoch_ms(event.get("timestamp"))
                if stamp is None:
                    continue
                record = _UsageRecord(
                    started_at=stamp,
                    cwd=event.get("cwd") or "(unknown)",
                    model_id=model_id,
                    input=usage.get("input_tokens") or 0,
                    output=usage.get("output_tokens") or 0,
                    reasoning=(
                        (usage.get("output_tokens_details") or {}).get("reasoning_tokens") or 0
                    ),
                    cache_write=usage.get("cache_creation_input_tokens") or 0,
                    cache_read=usage.get("cache_read_input_tokens") or 0,
                )
                if record.total <= 0:
                    continue  # 全零占位事件:不是计费事实
                message_id = message.get("id")
                if not message_id:
                    extras.append(record)
                    continue
                current = best.get(message_id)
                if current is None or _sum_of(record) > _sum_of(current):
                    best[message_id] = record
        records = list(best.values()) + extras
        if window is not None:
            records = [r for r in records if window.contains_day(ms_to_local_day(r.started_at))]
        return records

    def model_ids(self) -> list[str]:
        return sorted({r.model_id for r in self._records()})

    def model_keys(self, window: DateWindow | None = None) -> list[str]:
        return sorted({model_key(self.id, "claude", r.model_id) for r in self._records(window)})

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
            retention_hint=(
                _RETENTION_HINT if (self._config_dir / ".last-cleanup").exists() else None
            ),
        )

    def _summary_rows(self, window: DateWindow | None = None) -> list[ModelUsageSummary]:
        groups: dict[str, ModelUsageSummary] = {}
        for r in self._records(window):
            row = groups.get(r.model_id)
            if row is None:
                row = groups.setdefault(
                    r.model_id,
                    ModelUsageSummary(
                        source=self.id,
                        provider_id="claude",
                        model_id=r.model_id,
                        request_count=0,
                        input_tokens=0,
                        output_tokens=0,
                        reasoning_tokens=0,
                        cache_creation_tokens=0,
                        cache_read_tokens=0,
                        total_tokens=0,
                        tokens_reported=True,
                    ),
                )
            row.request_count += 1
            row.input_tokens += r.input
            row.output_tokens += r.output
            row.reasoning_tokens += r.reasoning
            row.cache_creation_tokens += r.cache_write
            row.cache_read_tokens += r.cache_read
            row.total_tokens += r.total
        return sorted(groups.values(), key=lambda m: m.total_tokens, reverse=True)

    def overview(self, window: DateWindow | None = None) -> Overview:
        records = self._records(window)
        ranked = self._summary_rows(window)
        totals = {
            "request_count": len(records),
            "input_tokens": sum(m.input_tokens for m in ranked),
            "output_tokens": sum(m.output_tokens for m in ranked),
            "reasoning_tokens": sum(m.reasoning_tokens for m in ranked),
            "cache_creation_tokens": sum(m.cache_creation_tokens for m in ranked),
            "cache_read_tokens": sum(m.cache_read_tokens for m in ranked),
            "total_tokens": sum(m.total_tokens for m in ranked),
        }
        return Overview(**totals, by_model=ranked)

    def daily_by_model(self, window: DateWindow | None = None) -> list[DailyModelUsage]:
        by_key: dict[tuple[str, str], list[_UsageRecord]] = {}
        for r in self._records(window):
            by_key.setdefault((ms_to_local_day(r.started_at), r.model_id), []).append(r)
        rows = [
            DailyModelUsage(
                source=self.id,
                day=day,
                provider_id="claude",
                model_id=model_id,
                request_count=len(bucket),
                input_tokens=sum(r.input for r in bucket),
                output_tokens=sum(r.output for r in bucket),
                reasoning_tokens=sum(r.reasoning for r in bucket),
                cache_creation_tokens=sum(r.cache_write for r in bucket),
                cache_read_tokens=sum(r.cache_read for r in bucket),
                total_tokens=sum(r.total for r in bucket),
                tokens_reported=True,
            )
            for (day, model_id), bucket in sorted(by_key.items())
        ]
        return sorted(rows, key=lambda m: (m.day, -m.total_tokens))

    def models_ranking(self, window: DateWindow | None = None) -> ModelsRanking:
        return ModelsRanking(models=list(self.overview(window).by_model))

    def usage_by_project_model(self) -> list[ProjectModelUsage]:
        by_key: dict[tuple[str, str], list[_UsageRecord]] = {}
        for r in self._records():
            by_key.setdefault((r.cwd, r.model_id), []).append(r)
        rows = [
            ProjectModelUsage(
                source=self.id,
                directory=directory,
                title=Path(directory).name or "(untitled)",
                provider_id="claude",
                model_id=model_id,
                request_count=len(bucket),
                input_tokens=sum(r.input for r in bucket),
                output_tokens=sum(r.output for r in bucket),
                reasoning_tokens=sum(r.reasoning for r in bucket),
                cache_creation_tokens=sum(r.cache_write for r in bucket),
                cache_read_tokens=sum(r.cache_read for r in bucket),
                total_tokens=sum(r.total for r in bucket),
                tokens_reported=True,
            )
            for (directory, model_id), bucket in sorted(by_key.items())
        ]
        return sorted(rows, key=lambda p: (p.directory, -p.total_tokens))

    def latency_samples(self, window: TimeWindow | None = None) -> tuple[list[int], list[int]]:
        return [], []  # upstream has no latency fields

    def health_summary(self, window: TimeWindow | None = None) -> HealthReport:
        records = self._records()
        if window is not None:
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

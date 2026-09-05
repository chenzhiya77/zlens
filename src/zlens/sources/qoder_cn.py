"""Read-only adapter over Qoder CN CLI's local transcripts (v3, T33).

Qoder CN CLI writes Claude-Code-shaped session transcripts under
``~/.qoder-cn/projects/<escaped-cwd>/``: main sessions as ``<sessionId>.jsonl``,
subagent transcripts as ``<sessionId>/subagents/agent-*.jsonl``. The metering
currency is credits, not tokens: ``message.usage`` carries
``credits``/``original_credits``/``billable``/``request_id`` while the four token
buckets are structurally zero — upstream never reports tokens, so this source
declares ``tokens_reported=False`` (the zeros are placeholders, never priced)
and its money lives entirely in the credit ledger.

Discounts are a per-row property (``original_credits`` vs ``credits`` — off-peak
0.5×/0.6× campaigns come and go with sessions), so both are kept per record and
summed as raw floats; credit values carry up to 9 decimals and are never
pre-rounded. Only ``entrypoint == "cli"`` records are accepted: if the IDE ever
writes the same tree, that gate is what keeps the two surfaces from
double-billing. Official session retention is 30 days (``.last-cleanup``
marker) — the local ledger is a sliding window, surfaced as a meta hint rather
than hidden.
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

_RETENTION_HINT = (
    "Qoder CN CLI 会话本地保留 30 天(官方 sessionRetention.maxAge=30d),"
    "更早的历史已不在本地,趋势图的时间边界由厂商清理决定。"
)


class _UsageRecord:
    __slots__ = ("started_at", "cwd", "model_id", "credits", "original_credits")

    def __init__(
        self,
        started_at: int,
        cwd: str,
        model_id: str,
        credits: float | None,
        original_credits: float | None,
    ) -> None:
        self.started_at = started_at
        self.cwd = cwd
        self.model_id = model_id
        self.credits = credits
        self.original_credits = original_credits


def _credit_or_none(value: object) -> float | None:
    """Absent/garbage → None (never coerced to 0); 0.0 passes through (real)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


class QoderCnSource:
    id = "qoder_cn"
    # Subclasses (international Qoder) override the text; the marker semantics
    # (official 30-day sessionRetention) are shared across CLI flavors.
    RETENTION_HINT = _RETENTION_HINT

    def __init__(self, config_dir: Path) -> None:
        self._config_dir = config_dir

    def is_available(self) -> bool:
        self._transcripts()
        return True

    def _transcripts(self) -> list[Path]:
        projects = self._config_dir / "projects"
        if not projects.is_dir():
            raise SourceUnavailable(f"Qoder CN projects directory not found: {projects}")
        # rglob picks up both main-session files and <session>/subagents/*.jsonl
        # (subagents bill independently — skipping them undercounts).
        return sorted(projects.rglob("*.jsonl"))

    def _records(self, window: DateWindow | None = None) -> list[_UsageRecord]:
        records: list[_UsageRecord] = []
        seen: set[str] = set()
        for path in self._transcripts():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a damaged line must not sink the whole source
                # CN CLI stamps metered records with type="assistant" (intl files
                # use "message"); both shapes carry message.role — require it.
                if event.get("type") not in ("assistant", "message"):
                    continue
                if (event.get("message") or {}).get("role") != "assistant":
                    continue
                if event.get("entrypoint") != "cli":
                    continue  # the anti-double-billing gate against IDE writes
                message = event.get("message") or {}
                usage = message.get("usage")
                if not usage:
                    continue
                model_id = message.get("model")
                if not model_id or model_id == "<synthetic>":
                    continue  # synthetic error records are not model calls
                stamp = iso_to_epoch_ms(event.get("timestamp"))
                if stamp is None:
                    continue
                # request_id is globally unique (verified 832/832 on real data):
                # the dedup key across main sessions and subagent transcripts.
                request_id = usage.get("request_id")
                if request_id:
                    if request_id in seen:
                        continue
                    seen.add(request_id)
                if window is not None and not window.contains_day(ms_to_local_day(stamp)):
                    continue  # load-level pushdown: the transcripts have no query layer
                credits = _credit_or_none(usage.get("credits"))
                original = _credit_or_none(usage.get("original_credits"))
                if usage.get("billable") is False:
                    # Failed/unbilled calls still count as requests but carry no
                    # credit charge — even if a value somehow rides along.
                    credits = None
                    original = None
                records.append(
                    _UsageRecord(
                        started_at=stamp,
                        cwd=event.get("cwd") or "(unknown)",
                        model_id=model_id,
                        credits=credits,
                        original_credits=original,
                    )
                )
        return records

    def model_ids(self) -> list[str]:
        return sorted({r.model_id for r in self._records()})

    def model_keys(self, window: DateWindow | None = None) -> list[str]:
        return sorted({model_key(self.id, "qoder", r.model_id) for r in self._records(window)})

    def _retention_hint(self) -> str | None:
        if (self._config_dir / ".last-cleanup").exists():
            return self.RETENTION_HINT
        return None

    def meta(self, window: DateWindow | None = None) -> MetaInfo:
        records = self._records(window)
        stamps = [r.started_at for r in records]
        return MetaInfo(
            source_id=self.id,
            request_count=len(records),
            first_request_at=ms_to_datetime(min(stamps)) if stamps else None,
            last_request_at=ms_to_datetime(max(stamps)) if stamps else None,
            generated_at=datetime.now().astimezone(),
            # Deliberately NOT in token_reporting_sources: the token buckets are
            # placeholders (tokens_reported=False), so this source must surface
            # in the "未计入 token 口径" hint instead.
            credit_reporting_sources=[self.id],
            retention_hint=self._retention_hint(),
        )

    def _summary_rows(self, window: DateWindow | None = None) -> list[ModelUsageSummary]:
        groups: dict[str, dict[str, object]] = {}
        for r in self._records(window):
            group = groups.setdefault(
                r.model_id,
                {
                    "row": ModelUsageSummary(
                        source=self.id,
                        provider_id="qoder",
                        model_id=r.model_id,
                        request_count=0,
                        input_tokens=0,
                        output_tokens=0,
                        reasoning_tokens=0,
                        cache_creation_tokens=0,
                        cache_read_tokens=0,
                        total_tokens=0,
                        tokens_reported=False,
                        credits_reported=True,
                    ),
                    "credits": 0.0,
                    "credits_seen": False,
                    "original": 0.0,
                    "original_seen": False,
                },
            )
            row: ModelUsageSummary = group["row"]  # type: ignore[assignment]
            row.request_count += 1
            if r.credits is not None:
                group["credits"] += r.credits  # type: ignore[assignment]
                group["credits_seen"] = True
            if r.original_credits is not None:
                group["original"] += r.original_credits  # type: ignore[assignment]
                group["original_seen"] = True
        rows: list[ModelUsageSummary] = []
        for group in groups.values():
            row: ModelUsageSummary = group["row"]  # type: ignore[assignment]
            if group["credits_seen"]:
                row.credits = round(group["credits"], 6)  # type: ignore[assignment]
            if group["original_seen"]:
                row.original_credits = round(group["original"], 6)  # type: ignore[assignment]
            rows.append(row)
        # 积分优先来源:按实扣积分降序(token 恒 0,total_tokens 排序无意义)
        return sorted(
            rows,
            key=lambda m: m.credits if m.credits is not None else -1.0,
            reverse=True,
        )

    def overview(self, window: DateWindow | None = None) -> Overview:
        records = self._records(window)
        ranked = self._summary_rows(window)
        credit_rows = [m for m in ranked if m.credits is not None]
        original_rows = [m for m in credit_rows if m.original_credits is not None]
        totals = {
            "request_count": len(records),
            "input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "total_tokens": 0,
        }
        return Overview(
            credits=(round(sum(m.credits for m in credit_rows), 6) if credit_rows else None),
            original_credits=(
                round(sum(m.original_credits for m in original_rows), 6) if original_rows else None
            ),
            tokens_reported=False,
            credits_reported=True,
            credit_reporting_sources=[self.id],
            token_reporting_sources=[],
            retention_hint=self._retention_hint(),
            **totals,
            by_model=ranked,
        )

    def daily_by_model(self, window: DateWindow | None = None) -> list[DailyModelUsage]:
        by_key: dict[tuple[str, str], list[_UsageRecord]] = {}
        for r in self._records(window):
            by_key.setdefault((ms_to_local_day(r.started_at), r.model_id), []).append(r)
        rows = [
            DailyModelUsage(
                source=self.id,
                day=day,
                provider_id="qoder",
                model_id=model_id,
                request_count=len(bucket),
                input_tokens=0,
                output_tokens=0,
                reasoning_tokens=0,
                cache_creation_tokens=0,
                cache_read_tokens=0,
                total_tokens=0,
                tokens_reported=False,
                credits_reported=True,
                credits=_bucket_sum(bucket, "credits"),
                original_credits=_bucket_sum(bucket, "original_credits"),
            )
            for (day, model_id), bucket in sorted(by_key.items())
        ]
        return sorted(rows, key=lambda m: (m.day, -m.request_count))

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
                provider_id="qoder",
                model_id=model_id,
                request_count=len(bucket),
                input_tokens=0,
                output_tokens=0,
                reasoning_tokens=0,
                cache_creation_tokens=0,
                cache_read_tokens=0,
                total_tokens=0,
                tokens_reported=False,
                credits_reported=True,
                credits=_bucket_sum(bucket, "credits"),
                original_credits=_bucket_sum(bucket, "original_credits"),
            )
            for (directory, model_id), bucket in sorted(by_key.items())
        ]
        return sorted(rows, key=lambda p: (p.directory, -p.request_count))

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


def _bucket_sum(records: list[_UsageRecord], field: str) -> float | None:
    """Ignore-null sum over the bucket; an all-absent bucket stays None."""
    values = [getattr(r, field) for r in records if getattr(r, field) is not None]
    return round(sum(values), 6) if values else None

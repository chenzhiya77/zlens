"""Read-only adapter over WorkBuddy's local transcript files (v3, T32).

WorkBuddy (Tencent) stores full agent transcripts per project directory:
``~/.workbuddy/projects/<project-slug>/<session-id>.jsonl`` — a Claude-Code-shaped
envelope whose assistant records carry three upstream usage dialects at once
(``message.usage``, ``providerData.rawUsage``, ``providerData.usage``). The
metering source is exactly one: ``providerData.rawUsage`` per assistant message.
``workbuddy.db`` is structurally excluded from metering — its ``session_usage``
duplicates the per-session credit totals, so reading both would bill every token
twice; every metered record carries its own ``cwd``, so the database is not even
needed for the project join.

Tier split (research §6.3, identities verified on real data): the cached prefix
sits *inside* ``prompt_tokens`` (Volcano/DeepSeek shape) —
``cache_read = prompt_cache_hit_tokens`` (equal to
``prompt_tokens_details.cached_tokens`` in every sampled record; hit tokens is
authoritative), ``cache_creation = prompt_cache_write_tokens``,
``input = prompt − read − write``, ``output = completion``, and the contract total
is the four-tier sum, checked against upstream ``total_tokens``. ``credit`` is per
message and 0.0 is a real value (Tencent's in-house hunyuan models bill zero
credits) — distinct from the field being absent, which leaves the group's credits
as None when no message in it carried one. Fields absent upstream (latency,
health beyond request counts) stay zero/empty rather than fabricated.
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
        "provider_id",
        "model_id",
        "cwd",
        "input",
        "output",
        "reasoning",
        "cache_write",
        "cache_read",
        "total",
        "credit",
    )

    def __init__(
        self,
        started_at: int,
        provider_id: str,
        model_id: str,
        cwd: str,
        input: int,
        output: int,
        reasoning: int,
        cache_write: int,
        cache_read: int,
        total: int,
        credit: float | None,
    ) -> None:
        self.started_at = started_at
        self.provider_id = provider_id
        self.model_id = model_id
        self.cwd = cwd
        self.input = input
        self.output = output
        self.reasoning = reasoning
        self.cache_write = cache_write
        self.cache_read = cache_read
        self.total = total
        self.credit = credit


class _ChannelGroup:
    """Per (tier, real model) accumulator — the channel key is tier × real model
    because one tier (e.g. `auto`) resolves to several real models and rows never
    merge across tiers or channels."""

    __slots__ = ("row", "credit_sum", "credit_seen")

    def __init__(self, provider_id: str, model_id: str) -> None:
        self.row = ModelUsageSummary(
            source="workbuddy",
            provider_id=provider_id,
            model_id=model_id,
            request_count=0,
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_tokens=0,
            tokens_reported=True,
            credits_reported=True,
        )
        self.credit_sum = 0.0
        self.credit_seen = False

    def add(self, r: _UsageRecord) -> None:
        self.row.request_count += 1
        self.row.input_tokens += r.input
        self.row.output_tokens += r.output
        self.row.reasoning_tokens += r.reasoning
        self.row.cache_creation_tokens += r.cache_write
        self.row.cache_read_tokens += r.cache_read
        self.row.total_tokens += r.total
        if r.credit is not None:
            self.credit_sum += r.credit
            self.credit_seen = True

    def finalize(self) -> ModelUsageSummary:
        if self.credit_seen:
            self.row.credits = round(self.credit_sum, 6)
        return self.row


def _bucket_credits(records: list[_UsageRecord]) -> float | None:
    """Sum of the credit values present in the bucket; 0.0 stays 0.0 (real free
    usage), and a bucket where no message carried the field stays None."""
    seen = [r.credit for r in records if r.credit is not None]
    return round(sum(seen), 6) if seen else None


class WorkbuddySource:
    id = "workbuddy"

    def __init__(self, root: Path) -> None:
        self._root = root

    def is_available(self) -> bool:
        self._transcripts()
        return True

    def _transcripts(self) -> list[Path]:
        projects = self._root / "projects"
        if not projects.is_dir():
            raise SourceUnavailable(f"WorkBuddy projects directory not found: {projects}")
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
                if event.get("type") != "message" or event.get("role") != "assistant":
                    continue
                provider = event.get("providerData") or {}
                usage = provider.get("rawUsage")
                if not usage:
                    continue  # helper/streaming records carry no usage payload
                stamp = event.get("timestamp")
                if stamp is None:
                    continue
                # messageId is the natural dedup key (top-level `id` mirrors it):
                # a replayed record must not bill twice.
                message_id = provider.get("messageId") or event.get("id")
                if message_id:
                    if message_id in seen:
                        continue
                    seen.add(message_id)
                if window is not None and not window.contains_day(ms_to_local_day(stamp)):
                    continue  # load-level pushdown: the transcripts have no query layer
                prompt = usage.get("prompt_tokens") or 0
                cache_read = usage.get("prompt_cache_hit_tokens") or 0
                cache_write = usage.get("prompt_cache_write_tokens") or 0
                output = usage.get("completion_tokens") or 0
                input_tokens = max(prompt - cache_read - cache_write, 0)
                details = usage.get("completion_tokens_details") or {}
                credit = usage.get("credit")
                if isinstance(credit, bool) or not isinstance(credit, (int, float)):
                    credit = None  # absent (or garbage) — never coerced to 0
                records.append(
                    _UsageRecord(
                        started_at=stamp,
                        # provider_id = the tier the user picked (auto/…); a tier
                        # can resolve to several real models, so the channel key
                        # is tier × real model (see _ChannelGroup).
                        provider_id=provider.get("requestModelId")
                        or provider.get("model")
                        or "unknown",
                        model_id=provider.get("model") or "unknown",
                        cwd=event.get("cwd") or "(unknown)",
                        input=input_tokens,
                        output=output,
                        reasoning=details.get("reasoning_tokens") or 0,
                        cache_write=cache_write,
                        cache_read=cache_read,
                        total=input_tokens + output + cache_read + cache_write,
                        credit=float(credit) if credit is not None else None,
                    )
                )
        return records

    def model_ids(self) -> list[str]:
        return sorted({r.model_id for r in self._records()})

    def model_keys(self, window: DateWindow | None = None) -> list[str]:
        return sorted(
            {model_key(self.id, r.provider_id, r.model_id) for r in self._records(window)}
        )

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
            credit_reporting_sources=[self.id],
        )

    def _summary_rows(self, window: DateWindow | None = None) -> list[ModelUsageSummary]:
        groups: dict[tuple[str, str], _ChannelGroup] = {}
        for r in self._records(window):
            key = (r.provider_id, r.model_id)
            group = groups.setdefault(key, _ChannelGroup(*key))
            group.add(r)
        return sorted(
            (group.finalize() for group in groups.values()),
            key=lambda m: m.total_tokens,
            reverse=True,
        )

    def overview(self, window: DateWindow | None = None) -> Overview:
        records = self._records(window)
        ranked = self._summary_rows(window)
        credit_rows = [m for m in ranked if m.credits is not None]
        totals = {
            "request_count": len(records),
            "input_tokens": sum(m.input_tokens for m in ranked),
            "output_tokens": sum(m.output_tokens for m in ranked),
            "reasoning_tokens": sum(m.reasoning_tokens for m in ranked),
            "cache_creation_tokens": sum(m.cache_creation_tokens for m in ranked),
            "cache_read_tokens": sum(m.cache_read_tokens for m in ranked),
            "total_tokens": sum(m.total_tokens for m in ranked),
        }
        return Overview(
            credits=(round(sum(m.credits for m in credit_rows), 6) if credit_rows else None),
            tokens_reported=True,
            credits_reported=True,
            credit_reporting_sources=[self.id],
            token_reporting_sources=[self.id],
            **totals,
            by_model=ranked,
        )

    def daily_by_model(self, window: DateWindow | None = None) -> list[DailyModelUsage]:
        by_key: dict[tuple[str, str, str], list[_UsageRecord]] = {}
        for r in self._records(window):
            key = (ms_to_local_day(r.started_at), r.provider_id, r.model_id)
            by_key.setdefault(key, []).append(r)
        rows = [
            DailyModelUsage(
                source=self.id,
                day=day,
                provider_id=provider_id,
                model_id=model_id,
                request_count=len(bucket),
                input_tokens=sum(r.input for r in bucket),
                output_tokens=sum(r.output for r in bucket),
                reasoning_tokens=sum(r.reasoning for r in bucket),
                cache_creation_tokens=sum(r.cache_write for r in bucket),
                cache_read_tokens=sum(r.cache_read for r in bucket),
                total_tokens=sum(r.total for r in bucket),
                tokens_reported=True,
                credits_reported=True,
                credits=_bucket_credits(bucket),
            )
            for (day, provider_id, model_id), bucket in sorted(by_key.items())
        ]
        return sorted(rows, key=lambda m: (m.day, -m.total_tokens))

    def models_ranking(self, window: DateWindow | None = None) -> ModelsRanking:
        return ModelsRanking(models=list(self.overview(window).by_model))

    def usage_by_project_model(self) -> list[ProjectModelUsage]:
        by_key: dict[tuple[str, str, str], list[_UsageRecord]] = {}
        for r in self._records():
            by_key.setdefault((r.cwd, r.provider_id, r.model_id), []).append(r)
        rows = [
            ProjectModelUsage(
                source=self.id,
                directory=directory,
                title=Path(directory).name or "(untitled)",
                provider_id=provider_id,
                model_id=model_id,
                request_count=len(bucket),
                input_tokens=sum(r.input for r in bucket),
                output_tokens=sum(r.output for r in bucket),
                reasoning_tokens=sum(r.reasoning for r in bucket),
                cache_creation_tokens=sum(r.cache_write for r in bucket),
                cache_read_tokens=sum(r.cache_read for r in bucket),
                total_tokens=sum(r.total for r in bucket),
                tokens_reported=True,
                credits_reported=True,
                credits=_bucket_credits(bucket),
            )
            for (directory, provider_id, model_id), bucket in sorted(by_key.items())
        ]
        return sorted(rows, key=lambda p: (p.directory, -p.total_tokens))

    def latency_samples(self, window: TimeWindow | None = None) -> tuple[list[int], list[int]]:
        return [], []  # upstream has no latency fields

    def health_summary(self, window: TimeWindow | None = None) -> HealthReport:
        records = self._records()
        if window is not None:
            # Transcripts load in bulk, so the instant window prunes here —
            # request_count is the only health field workbuddy can window at all.
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

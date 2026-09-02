"""Read-only adapter over opencode's local SQLite database.

Assistant messages store their request metadata as JSON in message.data. The
payload contains five token categories, model/provider identity and created /
completed timestamps; session.directory supplies the project dimension.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from zlens.sources.base import SchemaIncompatible, SourceUnavailable
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

_REQUIRED_COLUMNS = {
    "message": {"id", "session_id", "data"},
    "session": {"id", "directory", "title"},
}


class _UsageRecord:
    __slots__ = (
        "started_at",
        "completed_at",
        "provider_id",
        "model_id",
        "directory",
        "title",
        "input",
        "output",
        "reasoning",
        "cache_write",
        "cache_read",
        "total",
    )

    def __init__(
        self,
        *,
        started_at: int,
        completed_at: int | None,
        provider_id: str,
        model_id: str,
        directory: str | None,
        title: str | None,
        input: int,
        output: int,
        reasoning: int,
        cache_write: int,
        cache_read: int,
        total: int,
    ) -> None:
        self.started_at = started_at
        self.completed_at = completed_at
        self.provider_id = provider_id
        self.model_id = model_id
        self.directory = directory
        self.title = title
        self.input = input
        self.output = output
        self.reasoning = reasoning
        self.cache_write = cache_write
        self.cache_read = cache_read
        self.total = total


class OpencodeSource:
    id = "opencode"

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def is_available(self) -> bool:
        with self._cursor():
            return True

    def _records(self, window: DateWindow | None = None) -> list[_UsageRecord]:
        sql = (
            "SELECT m.data, s.directory, s.title"
            " FROM message m LEFT JOIN session s ON s.id = m.session_id"
        )
        params: list = []
        if window is not None:
            # Pushdown in SQL: the created ms lives inside message.data's JSON, so
            # extract it there. json_valid guards malformed payloads — they come
            # back NULL and drop out here exactly like the Python try/except below.
            created = "json_extract(CASE WHEN json_valid(m.data) THEN m.data END, '$.time.created')"
            conds = [f"{created} IS NOT NULL"]
            if window.start is not None:
                conds.append(f"date({created} / 1000, 'unixepoch', 'localtime') >= ?")
                params.append(window.start.isoformat())
            if window.end is not None:
                conds.append(f"date({created} / 1000, 'unixepoch', 'localtime') <= ?")
                params.append(window.end.isoformat())
            sql += " WHERE " + " AND ".join(conds)
        with self._cursor() as con:
            rows = con.execute(sql, params).fetchall()
        records: list[_UsageRecord] = []
        for row in rows:
            try:
                data = json.loads(row["data"])
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            tokens = data.get("tokens")
            time = data.get("time") or {}
            if data.get("role") != "assistant" or not tokens or time.get("created") is None:
                continue
            cache = tokens.get("cache") or {}
            reasoning = tokens.get("reasoning", 0)
            records.append(
                _UsageRecord(
                    started_at=time["created"],
                    completed_at=time.get("completed"),
                    provider_id=data.get("providerID") or "opencode",
                    model_id=data.get("modelID") or "unknown",
                    directory=row["directory"],
                    title=row["title"],
                    input=tokens.get("input", 0),
                    # opencode totals reasoning as its own addend; the contract bills
                    # it inside the output tier and keeps it as a breakdown only.
                    output=tokens.get("output", 0) + reasoning,
                    reasoning=reasoning,
                    cache_write=cache.get("write", 0),
                    cache_read=cache.get("read", 0),
                    total=tokens.get("total", 0),
                )
            )
        return records

    def model_ids(self) -> list[str]:
        return sorted({record.model_id for record in self._records()})

    def model_keys(self, window: DateWindow | None = None) -> list[str]:
        return sorted(
            {model_key(self.id, r.provider_id, r.model_id) for r in self._records(window)}
        )

    def meta(self, window: DateWindow | None = None) -> MetaInfo:
        records = self._records(window)
        stamps = [record.started_at for record in records]
        return MetaInfo(
            source_id=self.id,
            request_count=len(records),
            first_request_at=ms_to_datetime(min(stamps)) if stamps else None,
            last_request_at=ms_to_datetime(max(stamps)) if stamps else None,
            generated_at=datetime.now().astimezone(),
        )

    def overview(self, window: DateWindow | None = None) -> Overview:
        rows = self._model_rows(window)
        return Overview(
            request_count=sum(row.request_count for row in rows),
            input_tokens=sum(row.input_tokens for row in rows),
            output_tokens=sum(row.output_tokens for row in rows),
            reasoning_tokens=sum(row.reasoning_tokens for row in rows),
            cache_creation_tokens=sum(row.cache_creation_tokens for row in rows),
            cache_read_tokens=sum(row.cache_read_tokens for row in rows),
            total_tokens=sum(row.total_tokens for row in rows),
            by_model=rows,
        )

    def _model_rows(self, window: DateWindow | None = None) -> list[ModelUsageSummary]:
        acc: dict[tuple[str, str], ModelUsageSummary] = {}
        for record in self._records(window):
            key = (record.provider_id, record.model_id)
            row = acc.setdefault(
                key,
                ModelUsageSummary(
                    source=self.id,
                    provider_id=record.provider_id,
                    model_id=record.model_id,
                    request_count=0,
                    input_tokens=0,
                    output_tokens=0,
                    reasoning_tokens=0,
                    cache_creation_tokens=0,
                    cache_read_tokens=0,
                    total_tokens=0,
                ),
            )
            self._add_usage(row, record)
        return sorted(acc.values(), key=lambda row: row.total_tokens, reverse=True)

    @staticmethod
    def _add_usage(row, record: _UsageRecord) -> None:
        row.request_count += 1
        row.input_tokens += record.input
        row.output_tokens += record.output
        row.reasoning_tokens += record.reasoning
        row.cache_creation_tokens += record.cache_write
        row.cache_read_tokens += record.cache_read
        row.total_tokens += record.total

    def daily_by_model(self, window: DateWindow | None = None) -> list[DailyModelUsage]:
        acc: dict[tuple[str, str, str], DailyModelUsage] = {}
        for record in self._records(window):
            day = ms_to_local_day(record.started_at)
            key = (day, record.provider_id, record.model_id)
            row = acc.setdefault(
                key,
                DailyModelUsage(
                    source=self.id,
                    day=day,
                    provider_id=record.provider_id,
                    model_id=record.model_id,
                    request_count=0,
                    input_tokens=0,
                    output_tokens=0,
                    reasoning_tokens=0,
                    cache_creation_tokens=0,
                    cache_read_tokens=0,
                    total_tokens=0,
                ),
            )
            self._add_usage(row, record)
        return sorted(acc.values(), key=lambda row: (row.day, -row.total_tokens))

    def models_ranking(self, window: DateWindow | None = None) -> ModelsRanking:
        return ModelsRanking(models=self._model_rows(window))

    def usage_by_project_model(self) -> list[ProjectModelUsage]:
        acc: dict[tuple[str, str, str], ProjectModelUsage] = {}
        for record in self._records():
            directory = record.directory or "(unknown)"
            key = (directory, record.provider_id, record.model_id)
            row = acc.setdefault(
                key,
                ProjectModelUsage(
                    source=self.id,
                    directory=directory,
                    title=record.title or Path(directory).name or "(untitled)",
                    provider_id=record.provider_id,
                    model_id=record.model_id,
                    request_count=0,
                    input_tokens=0,
                    output_tokens=0,
                    reasoning_tokens=0,
                    cache_creation_tokens=0,
                    cache_read_tokens=0,
                    total_tokens=0,
                ),
            )
            self._add_usage(row, record)
        return sorted(acc.values(), key=lambda row: (row.directory, -row.total_tokens))

    def latency_samples(self, window: TimeWindow | None = None) -> tuple[list[int], list[int]]:
        records = self._records()
        if window is not None:
            records = [r for r in records if window.contains_ms(r.started_at)]
        durations = sorted(
            record.completed_at - record.started_at
            for record in records
            if record.completed_at is not None and record.completed_at >= record.started_at
        )
        return durations, []

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

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Connection]:
        con = self._connect()
        try:
            yield con
        finally:
            con.close()

    def _connect(self) -> sqlite3.Connection:
        if not self._db_path.exists():
            raise SourceUnavailable(f"opencode database not found: {self._db_path}")
        uri = f"file:{self._db_path.as_posix()}?mode=ro"
        try:
            con = sqlite3.connect(uri, uri=True, timeout=5.0)
        except sqlite3.Error as exc:
            raise SourceUnavailable(f"cannot open opencode database: {exc}") from exc
        con.row_factory = sqlite3.Row
        self._validate_schema(con)
        return con

    def _validate_schema(self, con: sqlite3.Connection) -> None:
        for table, required in _REQUIRED_COLUMNS.items():
            exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            if not exists:
                raise SchemaIncompatible(f"opencode table '{table}' missing")
            columns = {row["name"] for row in con.execute(f"PRAGMA table_info({table})")}
            missing = required - columns
            if missing:
                raise SchemaIncompatible(
                    f"opencode table '{table}' missing columns: {', '.join(sorted(missing))}"
                )

"""Read-only adapter over ZCode's own database.

The database belongs to a live application: every connection opens with SQLite's
read-only URI mode, all SQL lives in this module, and any failure degrades to a
SourceError instead of leaking a traceback (architecture rule in AGENTS.md).
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from zlens.sources.base import SchemaIncompatible, SourceUnavailable
from zlens.sources.models import (
    DailyModelUsage,
    ErrorGroup,
    HealthReport,
    MetaInfo,
    ModelsRanking,
    ModelUsageSummary,
    Overview,
    ProjectModelUsage,
    model_key,
)
from zlens.sources.timeutil import ms_to_datetime as _ms_to_datetime

# Columns this version aggregates. Kept explicit so upstream schema drift fails
# loudly here instead of producing silently wrong numbers.
_REQUIRED_COLUMNS = {
    "model_usage": {
        "provider_id",
        "model_id",
        "session_id",
        "started_at",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "computed_total_tokens",
        "duration_ms",
        "time_to_first_token_ms",
        "retry_count",
        "cancelled_by_user",
        "context_exceeded",
        "error_type",
        "error_code",
    },
    # Joined for the project dimension; required so a missing table degrades
    # loudly instead of 500-ing from inside the projects query.
    "session": {"id", "directory", "title"},
}

# ZCode bills the whole prompt as `input_tokens` and reports the cached prefix
# inside it (`cache_read_input_tokens` <= `input_tokens` on every row of the live
# db), while the app's contract is four mutually exclusive buckets that sum to
# total_tokens. So the cached part is subtracted here, per row and clamped — a
# single malformed record must not be able to offset a good one into a negative
# input. `reasoning_tokens` already sits inside `output_tokens`
# (computed_total_tokens == input + output on every row), hence untouched.
_AGGREGATE_SQL = """
    COUNT(*) AS request_count,
    COALESCE(SUM(MAX(
        COALESCE(input_tokens, 0) - COALESCE(cache_read_input_tokens, 0)
        - COALESCE(cache_creation_input_tokens, 0), 0)), 0) AS input_tokens,
    COALESCE(SUM(output_tokens), 0) AS output_tokens,
    COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
    COALESCE(SUM(cache_creation_input_tokens), 0) AS cache_creation_tokens,
    COALESCE(SUM(cache_read_input_tokens), 0) AS cache_read_tokens,
    COALESCE(SUM(computed_total_tokens), 0) AS total_tokens
"""

_AGGREGATE_KEYS = (
    "request_count",
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
    "total_tokens",
)


class ZcodeSource:
    id = "zcode"

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def is_available(self) -> bool:
        # Let SourceError subclasses propagate: the composite needs the specific
        # reason (unavailable vs schema_incompatible) to degrade accurately.
        with self._cursor():
            return True

    def model_ids(self) -> list[str]:
        with self._cursor() as con:
            rows = con.execute(
                "SELECT DISTINCT model_id FROM model_usage WHERE model_id IS NOT NULL"
            ).fetchall()
        return sorted(row["model_id"] for row in rows)

    def model_keys(self) -> list[str]:
        with self._cursor() as con:
            rows = con.execute(
                "SELECT DISTINCT provider_id, model_id FROM model_usage WHERE model_id IS NOT NULL"
            ).fetchall()
        return sorted(
            model_key(self.id, row["provider_id"] or "unknown", row["model_id"]) for row in rows
        )

    def meta(self) -> MetaInfo:
        with self._cursor() as con:
            row = con.execute(
                "SELECT COUNT(*) AS n,"
                " MIN(started_at) AS first_ms, MAX(started_at) AS last_ms"
                " FROM model_usage"
            ).fetchone()
        return MetaInfo(
            source_id=self.id,
            request_count=row["n"],
            first_request_at=_ms_to_datetime(row["first_ms"]),
            last_request_at=_ms_to_datetime(row["last_ms"]),
            generated_at=datetime.now().astimezone(),
        )

    def overview(self) -> Overview:
        with self._cursor() as con:
            totals = con.execute(f"SELECT {_AGGREGATE_SQL} FROM model_usage").fetchone()
            rows = con.execute(
                f"SELECT provider_id, model_id, {_AGGREGATE_SQL}"
                " FROM model_usage GROUP BY provider_id, model_id"
                " ORDER BY total_tokens DESC"
            ).fetchall()
        by_model = [
            ModelUsageSummary(
                source=self.id,
                provider_id=row["provider_id"] or "unknown",
                model_id=row["model_id"] or "unknown",
                **{key: row[key] for key in _AGGREGATE_KEYS},
            )
            for row in rows
        ]
        return Overview(**{key: totals[key] for key in _AGGREGATE_KEYS}, by_model=by_model)

    def daily_by_model(self) -> list[DailyModelUsage]:
        with self._cursor() as con:
            rows = con.execute(
                "SELECT date(started_at / 1000, 'unixepoch', 'localtime') AS day,"
                " provider_id, model_id,"
                f" {_AGGREGATE_SQL}"
                " FROM model_usage"
                " GROUP BY day, provider_id, model_id"
                " ORDER BY day, total_tokens DESC"
            ).fetchall()
        return [
            DailyModelUsage(
                source=self.id,
                day=row["day"],
                provider_id=row["provider_id"] or "unknown",
                model_id=row["model_id"] or "unknown",
                **{key: row[key] for key in _AGGREGATE_KEYS},
            )
            for row in rows
        ]

    def models_ranking(self) -> ModelsRanking:
        with self._cursor() as con:
            rows = con.execute(
                f"SELECT provider_id, model_id, {_AGGREGATE_SQL}"
                " FROM model_usage GROUP BY provider_id, model_id"
                " ORDER BY total_tokens DESC"
            ).fetchall()
        return ModelsRanking(
            models=[
                ModelUsageSummary(
                    source=self.id,
                    provider_id=row["provider_id"] or "unknown",
                    model_id=row["model_id"] or "unknown",
                    **{key: row[key] for key in _AGGREGATE_KEYS},
                )
                for row in rows
            ]
        )

    def usage_by_project_model(self) -> list[ProjectModelUsage]:
        with self._cursor() as con:
            rows = con.execute(
                "SELECT COALESCE(NULLIF(s.directory, ''), '(unknown)') AS directory,"
                " COALESCE(NULLIF(MAX(s.title), ''), '(untitled)') AS title,"
                " mu.provider_id AS provider_id, mu.model_id AS model_id,"
                f" {_AGGREGATE_SQL}"
                " FROM model_usage mu"
                " LEFT JOIN session s ON s.id = mu.session_id"
                " GROUP BY directory, mu.provider_id, mu.model_id"
                " ORDER BY directory, total_tokens DESC"
            ).fetchall()
        return [
            ProjectModelUsage(
                source=self.id,
                directory=row["directory"],
                title=row["title"],
                provider_id=row["provider_id"] or "unknown",
                model_id=row["model_id"] or "unknown",
                **{key: row[key] for key in _AGGREGATE_KEYS},
            )
            for row in rows
        ]

    def latency_samples(self) -> tuple[list[int], list[int]]:
        with self._cursor() as con:
            durations = [
                row[0]
                for row in con.execute(
                    "SELECT duration_ms FROM model_usage"
                    " WHERE duration_ms IS NOT NULL ORDER BY duration_ms"
                )
            ]
            ttfts = [
                row[0]
                for row in con.execute(
                    "SELECT time_to_first_token_ms FROM model_usage"
                    " WHERE time_to_first_token_ms IS NOT NULL"
                    " ORDER BY time_to_first_token_ms"
                )
            ]
        return durations, ttfts

    def health_summary(self) -> HealthReport:
        with self._cursor() as con:
            row = con.execute(
                "SELECT COUNT(*) AS request_count,"
                " COALESCE(SUM(CASE WHEN retry_count > 0 THEN 1 ELSE 0 END), 0)"
                "   AS requests_with_retries,"
                " COALESCE(SUM(retry_count), 0) AS total_retries,"
                " COALESCE(SUM(CASE WHEN cancelled_by_user = 1 THEN 1 ELSE 0 END), 0)"
                "   AS cancelled_by_user,"
                " COALESCE(SUM(CASE WHEN context_exceeded = 1 THEN 1 ELSE 0 END), 0)"
                "   AS context_exceeded,"
                " COALESCE(SUM(CASE WHEN error_type IS NOT NULL THEN 1 ELSE 0 END), 0)"
                "   AS errored_requests"
                " FROM model_usage"
            ).fetchone()
            error_rows = con.execute(
                "SELECT error_type, error_code, COUNT(*) AS n"
                " FROM model_usage WHERE error_type IS NOT NULL"
                " GROUP BY error_type, error_code ORDER BY n DESC, error_type"
            ).fetchall()
        return HealthReport(
            request_count=row["request_count"],
            requests_with_retries=row["requests_with_retries"],
            total_retries=row["total_retries"],
            cancelled_by_user=row["cancelled_by_user"],
            context_exceeded=row["context_exceeded"],
            errored_requests=row["errored_requests"],
            errors=[
                ErrorGroup(
                    source=self.id,
                    error_type=r["error_type"],
                    error_code=r["error_code"],
                    request_count=r["n"],
                )
                for r in error_rows
            ],
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
            raise SourceUnavailable(f"database not found: {self._db_path}")
        uri = f"file:{self._db_path.as_posix()}?mode=ro"
        try:
            con = sqlite3.connect(uri, uri=True, timeout=5.0)
        except sqlite3.Error as exc:
            raise SourceUnavailable(f"cannot open database: {exc}") from exc
        con.row_factory = sqlite3.Row
        self._validate_schema(con)
        return con

    def _validate_schema(self, con: sqlite3.Connection) -> None:
        for table, required in _REQUIRED_COLUMNS.items():
            exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            if not exists:
                raise SchemaIncompatible(f"table '{table}' missing")
            columns = {row["name"] for row in con.execute(f"PRAGMA table_info({table})")}
            missing = required - columns
            if missing:
                raise SchemaIncompatible(
                    f"table '{table}' missing columns: {', '.join(sorted(missing))}"
                )

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

from zlens.sources.base import SchemaIncompatible, SourceError, SourceUnavailable
from zlens.sources.models import MetaInfo, ModelUsageSummary, Overview

# Columns this version aggregates. Kept explicit so upstream schema drift fails
# loudly here instead of producing silently wrong numbers.
_REQUIRED_COLUMNS = {
    "model_usage": {
        "provider_id",
        "model_id",
        "started_at",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "computed_total_tokens",
    }
}

_AGGREGATE_SQL = """
    COUNT(*) AS request_count,
    COALESCE(SUM(input_tokens), 0) AS input_tokens,
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


def _ms_to_datetime(ms: int | None) -> datetime | None:
    return None if ms is None else datetime.fromtimestamp(ms / 1000).astimezone()


class ZcodeSource:
    id = "zcode"

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def is_available(self) -> bool:
        try:
            with self._cursor():
                return True
        except SourceError:
            return False

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
                provider_id=row["provider_id"] or "unknown",
                model_id=row["model_id"] or "unknown",
                **{key: row[key] for key in _AGGREGATE_KEYS},
            )
            for row in rows
        ]
        return Overview(**{key: totals[key] for key in _AGGREGATE_KEYS}, by_model=by_model)

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

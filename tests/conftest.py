"""Synthetic ZCode database fixtures mirroring the schema zlens queries.

Rows are dicts keyed by column name; unspecified columns fall back to the
table defaults (0 for token counters, NULL for timestamps/errors). Offline by
default: no test may touch the real ~/.zcode database unless marked `live`.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zlens.api.app import create_app
from zlens.core.config import Settings

_CREATE_MODEL_USAGE = """
CREATE TABLE model_usage (
    id INTEGER PRIMARY KEY,
    provider_id TEXT,
    model_id TEXT,
    session_id TEXT,
    started_at INTEGER,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    cache_creation_input_tokens INTEGER DEFAULT 0,
    cache_read_input_tokens INTEGER DEFAULT 0,
    computed_total_tokens INTEGER DEFAULT 0,
    duration_ms INTEGER,
    time_to_first_token_ms INTEGER,
    retry_count INTEGER DEFAULT 0,
    cancelled_by_user INTEGER DEFAULT 0,
    context_exceeded INTEGER DEFAULT 0,
    error_type TEXT,
    error_code TEXT
)
"""

_CREATE_SESSION = """
CREATE TABLE session (
    id TEXT PRIMARY KEY,
    directory TEXT,
    title TEXT
)
"""


def write_db(path: Path, rows, sessions=()) -> Path:
    con = sqlite3.connect(path)
    try:
        con.execute(_CREATE_MODEL_USAGE)
        con.execute(_CREATE_SESSION)
        for row in rows:
            columns = list(row)
            if not columns:
                con.execute("INSERT INTO model_usage DEFAULT VALUES")
                continue
            placeholders = ", ".join("?" * len(columns))
            con.execute(
                f"INSERT INTO model_usage ({', '.join(columns)}) VALUES ({placeholders})",
                [row[c] for c in columns],
            )
        con.executemany("INSERT INTO session (id, directory, title) VALUES (?, ?, ?)", sessions)
        con.commit()
    finally:
        con.close()
    return path


@pytest.fixture
def make_db(tmp_path):
    """Factory: build a synthetic ZCode database, return its path."""

    def _make(rows=(), sessions=()):
        return write_db(tmp_path / "zcode.sqlite", rows, sessions)

    return _make


@pytest.fixture
def client_factory(make_db):
    """Factory: app + TestClient bound to a synthetic database."""

    def _make(rows=(), sessions=()):
        return TestClient(create_app(Settings(db_path=make_db(rows, sessions))))

    return _make

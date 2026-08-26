"""Synthetic ZCode database fixtures mirroring the schema zlens queries.

Offline by default: no test may touch the real ~/.zcode database unless it is
marked `live` (see AGENTS.md).
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
    started_at INTEGER,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    cache_creation_input_tokens INTEGER DEFAULT 0,
    cache_read_input_tokens INTEGER DEFAULT 0,
    computed_total_tokens INTEGER DEFAULT 0
)
"""

_INSERT = """
INSERT INTO model_usage
    (provider_id, model_id, started_at, input_tokens, output_tokens, reasoning_tokens,
     cache_creation_input_tokens, cache_read_input_tokens, computed_total_tokens)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def write_db(path: Path, rows) -> Path:
    con = sqlite3.connect(path)
    try:
        con.execute(_CREATE_MODEL_USAGE)
        con.executemany(_INSERT, rows)
        con.commit()
    finally:
        con.close()
    return path


@pytest.fixture
def make_db(tmp_path):
    """Factory: build a synthetic ZCode database, return its path."""

    def _make(rows):
        return write_db(tmp_path / "zcode.sqlite", rows)

    return _make


@pytest.fixture
def client_factory(make_db):
    """Factory: app + TestClient bound to a synthetic database."""

    def _make(rows):
        return TestClient(create_app(Settings(db_path=make_db(rows))))

    return _make

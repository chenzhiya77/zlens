"""Synthetic source fixtures mirroring the formats zlens reads.

Rows are dicts keyed by column name; unspecified columns fall back to the
table defaults (0 for token counters, NULL for timestamps/errors). Offline by
default: no test may touch real agent data unless marked `live`.

Multi-source isolation: Settings always pin the other sources to nonexistent
paths so a test only ever sees what it built.
"""

import json
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
def make_minimax_sessions(tmp_path):
    """Factory: build a synthetic MiniMax sessions directory, return its path."""

    def _make(sessions):
        root = tmp_path / "minimax" / "v2" / "sessions"
        for index, spec in enumerate(sessions):
            sdir = root / "2026" / "08" / "04" / f"{index:02d}-00-00-000-session_fx{index}"
            sdir.mkdir(parents=True)
            lines = []
            workspace = spec.get("workspace")
            if workspace is not None:
                lines.append(
                    json.dumps(
                        {
                            "kind": "session.created",
                            "createdAtMs": spec["events"][0]["ms"],
                            "record": {"workspaceDir": workspace},
                        }
                    )
                )
            for event in spec["events"]:
                lines.append(
                    json.dumps(
                        {
                            "kind": "message.update",
                            "createdAtMs": event["ms"],
                            "messages": [
                                {
                                    "usage": {
                                        "input": event["input"],
                                        "output": event["output"],
                                        "cacheRead": event.get("cache_read", 0),
                                        "cacheWrite": event.get("cache_write", 0),
                                        "totalTokens": event["total"],
                                    }
                                }
                            ],
                        }
                    )
                )
            (sdir / "ledger.jsonl").write_text("\n".join(lines), encoding="utf-8")
            if spec.get("model"):
                (sdir / "display.jsonl").write_text(
                    json.dumps({"model": spec["model"]}) + "\n", encoding="utf-8"
                )
        return root

    return _make


@pytest.fixture
def make_opencode_db(tmp_path):
    """Factory: build a minimal opencode SQLite database with JSON messages."""

    def _make(messages, sessions=()):
        path = tmp_path / "opencode.db"
        con = sqlite3.connect(path)
        try:
            con.execute(
                "CREATE TABLE session ("
                "id TEXT PRIMARY KEY, project_id TEXT, directory TEXT, title TEXT)"
            )
            con.execute(
                "CREATE TABLE message ("
                "id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER,"
                " time_updated INTEGER, data TEXT)"
            )
            con.executemany(
                "INSERT INTO session (id, project_id, directory, title) VALUES (?, ?, ?, ?)",
                sessions,
            )
            con.executemany(
                "INSERT INTO message (id, session_id, time_created, time_updated, data) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        message["id"],
                        message["session_id"],
                        message.get("created", 0),
                        message.get("created", 0),
                        json.dumps(message["data"]),
                    )
                    for message in messages
                ],
            )
            con.commit()
        finally:
            con.close()
        return path

    return _make


@pytest.fixture
def make_workbuddy(tmp_path):
    """Factory: build a synthetic WorkBuddy root — projects transcripts (the only
    metered source) plus the twin workbuddy.db whose session_usage duplicates
    per-session credit totals (the adapter must ignore it entirely)."""

    def _make(sessions, session_usage=()):
        root = tmp_path / "workbuddy"
        projects = root / "projects"
        for spec in sessions:
            sdir = projects / spec["project_slug"]
            sdir.mkdir(parents=True, exist_ok=True)
            lines = [json.dumps(record) for record in spec["records"]]
            (sdir / f"{spec['session_id']}.jsonl").write_text("\n".join(lines), encoding="utf-8")
        if session_usage:
            con = sqlite3.connect(root / "workbuddy.db")
            try:
                con.execute(
                    "CREATE TABLE sessions ("
                    "id TEXT PRIMARY KEY, cwd TEXT, title TEXT, custom_title TEXT)"
                )
                con.execute(
                    "CREATE TABLE session_usage ("
                    "session_id TEXT PRIMARY KEY, used INTEGER, size INTEGER, credit_json TEXT)"
                )
                con.executemany(
                    "INSERT INTO sessions (id, cwd, title, custom_title) VALUES (?, ?, ?, ?)",
                    [(s[0], s[1], s[2], None) for s in session_usage],
                )
                con.executemany(
                    "INSERT INTO session_usage (session_id, used, size, credit_json) "
                    "VALUES (?, ?, ?, ?)",
                    session_usage,
                )
                con.commit()
            finally:
                con.close()
        return root

    return _make


@pytest.fixture
def make_qoder_cn(tmp_path):
    """Factory: synthetic Qoder CN CLI root — main-session transcripts, optional
    per-session subagent transcripts, optional .last-cleanup retention marker."""

    def _make(sessions, last_cleanup=False):
        root = tmp_path / "qoder-cn"
        projects = root / "projects"
        for spec in sessions:
            cwd_dir = projects / spec["project_slug"]
            cwd_dir.mkdir(parents=True, exist_ok=True)
            lines = [json.dumps(record) for record in spec["records"]]
            (cwd_dir / f"{spec['session_id']}.jsonl").write_text("\n".join(lines), encoding="utf-8")
            for sub in spec.get("subagents", []):
                sdir = cwd_dir / spec["session_id"] / "subagents"
                sdir.mkdir(parents=True, exist_ok=True)
                (sdir / sub["name"]).write_text(
                    "\n".join(json.dumps(record) for record in sub["records"]),
                    encoding="utf-8",
                )
        if last_cleanup:
            (root / ".last-cleanup").write_text("{}", encoding="utf-8")
        return root

    return _make


@pytest.fixture
def make_settings(
    tmp_path, make_db, make_minimax_sessions, make_opencode_db, make_workbuddy, make_qoder_cn
):
    """Settings where only the explicitly built sources exist."""

    def _make(
        rows=(),
        sessions=(),
        minimax=(),
        opencode=None,
        opencode_sessions=(),
        workbuddy=None,
        workbuddy_usage=(),
        qoder_cn=None,
        qoder_cn_last_cleanup=False,
        pricing_path=None,
        config_json_path=None,
    ):
        return Settings(
            db_path=make_db(rows, sessions),
            minimax_sessions_dir=(
                make_minimax_sessions(minimax) if minimax else tmp_path / "minimax-missing"
            ),
            opencode_db_path=(
                make_opencode_db(opencode, opencode_sessions)
                if opencode is not None
                else tmp_path / "opencode-missing.db"
            ),
            workbuddy_dir=(
                make_workbuddy(workbuddy, workbuddy_usage)
                if workbuddy
                else tmp_path / "workbuddy-missing"
            ),
            qoder_cn_config_dir=(
                make_qoder_cn(qoder_cn, qoder_cn_last_cleanup)
                if qoder_cn
                else tmp_path / "qoder-cn-missing"
            ),
            pricing_path=(pricing_path or tmp_path / "pricing.json"),
            config_json_path=(config_json_path or tmp_path / "zlens.config.json"),
        )

    return _make


@pytest.fixture
def client_factory(make_settings):
    """Factory: app + TestClient bound to synthetic sources."""

    def _make(rows=(), sessions=(), minimax=(), **kwargs):
        return TestClient(create_app(make_settings(rows, sessions, minimax, **kwargs)))

    return _make

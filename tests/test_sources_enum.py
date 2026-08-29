"""T18: /api/meta.sources enumerates every registered source — available or not,
with the probe error as its reason — while source_id keeps its old meaning.
"""

import sqlite3
from datetime import datetime

from fastapi.testclient import TestClient

from zlens.api.app import create_app
from zlens.core.config import Settings


def _ms(day: str) -> int:
    dt = datetime.fromisoformat(f"{day}T12:00:00").astimezone()
    return int(dt.timestamp() * 1000)


def _client_with(client_factory):
    # One healthy zcode + two dead sources (missing paths) is the default shape of
    # make_settings; assert against that before adding a schema-broken variant.
    return client_factory(
        rows=[
            {
                "provider_id": "p",
                "model_id": "m1",
                "started_at": _ms("2026-08-01"),
                "computed_total_tokens": 10,
            },
        ]
    )


def test_sources_list_includes_unavailable_with_reason(client_factory):
    client = _client_with(client_factory)

    body = client.get("/api/meta").json()

    ids = [s["id"] for s in body["sources"]]
    assert ids == ["zcode", "minimax", "opencode"]  # registered, not merely active
    by_id = {s["id"]: s for s in body["sources"]}
    assert by_id["zcode"]["available"] is True
    assert by_id["zcode"]["error"] is None
    assert by_id["minimax"]["available"] is False
    assert "not found" in by_id["minimax"]["error"]
    assert by_id["opencode"]["available"] is False
    assert by_id["opencode"]["error"]


def test_source_id_keeps_its_legacy_plus_joined_shape(client_factory):
    client = _client_with(client_factory)

    body = client.get("/api/meta").json()

    assert body["source_id"] == "zcode"


def test_schema_broken_source_reports_its_reason(tmp_path, make_db):
    """A source that exists but drifted schema keeps its slot with the reason.
    At least one healthy source stays up so /api/meta serves instead of 503."""
    broken = tmp_path / "broken-opencode.sqlite"
    con = sqlite3.connect(broken)
    con.execute("CREATE TABLE message (id TEXT PRIMARY KEY)")  # missing columns
    con.commit()
    con.close()
    settings = Settings(
        db_path=make_db(
            [
                {
                    "provider_id": "p",
                    "model_id": "m1",
                    "started_at": _ms("2026-08-01"),
                    "computed_total_tokens": 10,
                }
            ]
        ),
        minimax_sessions_dir=tmp_path / "minimax-missing",
        opencode_db_path=broken,
    )
    client = TestClient(create_app(settings))

    body = client.get("/api/meta").json()

    by_id = {s["id"]: s for s in body["sources"]}
    assert by_id["zcode"]["available"] is True
    assert by_id["opencode"]["available"] is False
    assert "missing columns" in by_id["opencode"]["error"]


def test_enumeration_survives_source_selection_and_window(client_factory):
    client = _client_with(client_factory)

    body = client.get(
        "/api/meta", params={"source": "zcode", "start": "2026-01-01", "end": "2026-12-31"}
    ).json()

    assert [s["id"] for s in body["sources"]] == ["zcode", "minimax", "opencode"]
    assert body["request_count"] == 1

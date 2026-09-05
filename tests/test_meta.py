from datetime import datetime

from fastapi.testclient import TestClient

from zlens.api.app import create_app
from zlens.core.config import Settings


def test_meta_reports_count_and_local_time_range(client_factory):
    rows = [
        {"provider_id": "p", "model_id": "m1", "started_at": 1_700_000_000_000},
        {"provider_id": "p", "model_id": "m1", "started_at": 1_700_000_100_000},
    ]
    body = client_factory(rows).get("/api/meta").json()

    assert body["source_id"] == "zcode"
    assert body["request_count"] == 2
    assert (
        datetime.fromisoformat(body["first_request_at"])
        == datetime.fromtimestamp(1_700_000_000).astimezone()
    )
    assert (
        datetime.fromisoformat(body["last_request_at"])
        == datetime.fromtimestamp(1_700_000_100).astimezone()
    )
    assert body["generated_at"]


def test_meta_on_empty_database(client_factory):
    body = client_factory([]).get("/api/meta").json()

    assert body["request_count"] == 0
    assert body["first_request_at"] is None
    assert body["last_request_at"] is None


def test_meta_carries_package_version(client_factory):
    """T23 D7: the footer version comes from zlens.__version__, never hardcoded
    in the SPA — so /api/meta must stamp the real package version."""
    import zlens

    body = client_factory([]).get("/api/meta").json()

    assert body["version"] == zlens.__version__


def test_missing_database_reports_source_unavailable(tmp_path):
    settings = Settings(
        db_path=tmp_path / "absent.sqlite",
        minimax_sessions_dir=tmp_path / "minimax-missing",
        opencode_db_path=tmp_path / "opencode-missing.db",
        workbuddy_dir=tmp_path / "workbuddy-missing",
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/meta")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"


def test_broken_schema_reports_schema_incompatible(tmp_path):
    import sqlite3

    path = tmp_path / "broken.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE model_usage (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()

    client = TestClient(
        create_app(
            Settings(
                db_path=path,
                minimax_sessions_dir=tmp_path / "minimax-missing",
                opencode_db_path=tmp_path / "opencode-missing.db",
                workbuddy_dir=tmp_path / "workbuddy-missing",
            )
        )
    )

    response = client.get("/api/meta")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "schema_incompatible"

from datetime import datetime

from fastapi.testclient import TestClient

from zlens.api.app import create_app
from zlens.core.config import Settings


def test_meta_reports_count_and_local_time_range(client_factory):
    rows = [
        ("p", "m1", 1_700_000_000_000, 10, 5, 0, 0, 0, 15),
        ("p", "m1", 1_700_000_100_000, 20, 5, 0, 0, 0, 25),
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


def test_missing_database_reports_source_unavailable(tmp_path):
    client = TestClient(create_app(Settings(db_path=tmp_path / "absent.sqlite")))

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

    client = TestClient(create_app(Settings(db_path=path)))

    response = client.get("/api/meta")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "schema_incompatible"

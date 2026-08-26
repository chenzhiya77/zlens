"""Live smoke tests against the real local database (excluded by default)."""

import pytest
from fastapi.testclient import TestClient

from zlens.api.app import create_app
from zlens.core.config import load_settings


@pytest.mark.live
def test_real_database_serves_meta_and_overview():
    settings = load_settings()
    if not settings.db_path.exists():
        pytest.skip("real ZCode database not present on this machine")

    client = TestClient(create_app(settings))

    meta = client.get("/api/meta")
    assert meta.status_code == 200
    assert meta.json()["request_count"] > 0
    assert client.get("/api/overview").status_code == 200

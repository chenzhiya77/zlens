"""T20: backend-computed grand totals on /api/overview.

Same honesty rule as ever: token buckets are upstream facts and always sum;
the cost total is null while any served model is unpriced.
"""

import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from zlens.api.app import create_app


def _ms(day: str) -> int:
    dt = datetime.fromisoformat(f"{day}T12:00:00").astimezone()
    return int(dt.timestamp() * 1000)


_ROWS = [
    {
        "provider_id": "chan-a",
        "model_id": "model-a",
        "started_at": _ms("2026-08-01"),
        "input_tokens": 1_000_000,
        "computed_total_tokens": 1_000_000,
    },
    {
        "provider_id": "chan-b",
        "model_id": "model-b",
        "started_at": _ms("2026-08-15"),
        "input_tokens": 500_000,
        "computed_total_tokens": 500_000,
    },
]

_PRICES = {
    "zcode|chan-a|model-a": {"input": 1.0, "output": 0.0},
    "zcode|chan-b|model-b": {"input": 2.0, "output": 0.0},
}


@pytest.fixture
def client(make_settings, tmp_path):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps({"version": 1, "models": _PRICES}), encoding="utf-8")
    return TestClient(create_app(make_settings(rows=_ROWS, pricing_path=pricing_path)))


def test_fully_priced_totals_equal_sum_of_models(client):
    body = client.get("/api/overview").json()

    assert body["totals"]["estimated_cost"] == 2.0  # 1M×¥1 + 0.5M×¥2
    assert body["totals"]["total_tokens"] == 1_500_000
    assert body["totals"]["request_count"] == 2


def test_unpriced_model_nulls_cost_total_but_tokens_still_sum(make_settings, tmp_path):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps({"version": 1, "models": {"zcode|chan-a|model-a": {"input": 1.0}}}),
        encoding="utf-8",
    )
    client = TestClient(create_app(make_settings(rows=_ROWS, pricing_path=pricing_path)))

    body = client.get("/api/overview").json()

    assert body["totals"]["estimated_cost"] is None
    assert body["totals"]["total_tokens"] == 1_500_000
    assert body["totals"]["input_tokens"] == 1_500_000


def test_totals_follow_window_and_source(client):
    windowed = client.get(
        "/api/overview", params={"start": "2026-08-15", "end": "2026-08-15"}
    ).json()
    assert windowed["totals"]["total_tokens"] == 500_000
    assert windowed["totals"]["estimated_cost"] == 1.0

    per_source = client.get("/api/overview", params={"source": "zcode"}).json()
    assert per_source["totals"]["total_tokens"] == 1_500_000

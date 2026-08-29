"""T19: backend-side table sort on /api/overview and /api/models.

Defaults keep today's order (total_tokens desc); unpriced rows always sink to
the bottom, whichever direction — "unknown" must never read as "cheap".
"""

import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from zlens.api.app import create_app

_DAY_A = "2026-08-01"
_DAY_B = "2026-08-20"


def _ms(day: str) -> int:
    dt = datetime.fromisoformat(f"{day}T12:00:00").astimezone()
    return int(dt.timestamp() * 1000)


_ROWS = [
    # model-a: priced, 2 requests, 4M tok, cost ¥4.0 (both days)
    {
        "provider_id": "chan-a",
        "model_id": "model-a",
        "started_at": _ms(_DAY_A),
        "input_tokens": 1_000_000,
        "computed_total_tokens": 1_000_000,
    },
    {
        "provider_id": "chan-a",
        "model_id": "model-a",
        "started_at": _ms(_DAY_B),
        "input_tokens": 3_000_000,
        "computed_total_tokens": 3_000_000,
    },
    # model-b: priced, 1 request, 0.5M tok, cost ¥0.5
    {
        "provider_id": "chan-b",
        "model_id": "model-b",
        "started_at": _ms(_DAY_A),
        "input_tokens": 500_000,
        "computed_total_tokens": 500_000,
    },
    # model-c: unpriced, 3 requests, 1.1M tok — cost stays None
    {
        "provider_id": "chan-c",
        "model_id": "model-c",
        "started_at": _ms(_DAY_A),
        "input_tokens": 900_000,
        "computed_total_tokens": 900_000,
    },
    {
        "provider_id": "chan-c",
        "model_id": "model-c",
        "started_at": _ms(_DAY_A),
        "input_tokens": 100_000,
        "computed_total_tokens": 100_000,
    },
    {
        "provider_id": "chan-c",
        "model_id": "model-c",
        "started_at": _ms(_DAY_A),
        "input_tokens": 100_000,
        "computed_total_tokens": 100_000,
    },
]

_PRICES = {
    "zcode|chan-a|model-a": {"input": 1.0, "output": 0.0},
    "zcode|chan-b|model-b": {"input": 1.0, "output": 0.0},
}


@pytest.fixture
def client(make_settings, tmp_path):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps({"version": 1, "models": _PRICES}), encoding="utf-8")
    return TestClient(create_app(make_settings(rows=_ROWS, pricing_path=pricing_path)))


def test_default_sort_is_total_tokens_desc(client):
    body = client.get("/api/overview").json()

    assert [m["model_id"] for m in body["by_model"]] == ["model-a", "model-c", "model-b"]


def test_sort_by_cost_puts_unpriced_last_regardless_of_direction(client):
    desc = client.get("/api/overview", params={"sort": "estimated_cost", "order": "desc"}).json()
    assert [(m["model_id"], m["estimated_cost"]) for m in desc["by_model"]] == [
        ("model-a", 4.0),
        ("model-b", 0.5),
        ("model-c", None),  # unknown, not cheap
    ]

    asc = client.get("/api/overview", params={"sort": "estimated_cost", "order": "asc"}).json()
    assert [(m["model_id"], m["estimated_cost"]) for m in asc["by_model"]] == [
        ("model-b", 0.5),
        ("model-a", 4.0),
        ("model-c", None),  # still last, not first
    ]


def test_sort_by_request_count(client):
    body = client.get("/api/overview", params={"sort": "request_count"}).json()

    assert [(m["model_id"], m["request_count"]) for m in body["by_model"]] == [
        ("model-c", 3),
        ("model-a", 2),
        ("model-b", 1),
    ]


def test_unknown_sort_or_order_is_422_with_allowed_values(client):
    bad_sort = client.get("/api/overview", params={"sort": "cache_read_tokens"})
    assert bad_sort.status_code == 422
    assert "total_tokens" in str(bad_sort.json())

    bad_order = client.get("/api/overview", params={"order": "up"})
    assert bad_order.status_code == 422


def test_sort_combines_with_window(client):
    body = client.get(
        "/api/overview",
        params={"start": _DAY_B, "end": _DAY_B, "sort": "request_count", "order": "asc"},
    ).json()

    # Only model-a has rows on _DAY_B (1 request); the unpriced row fell out of
    # the window entirely.
    assert [(m["model_id"], m["request_count"]) for m in body["by_model"]] == [("model-a", 1)]


def test_models_endpoint_honors_sort(client):
    body = client.get("/api/models", params={"sort": "estimated_cost", "order": "asc"}).json()

    assert [(m["model_id"], m["estimated_cost"]) for m in body["models"]] == [
        ("model-b", 0.5),
        ("model-a", 4.0),
        ("model-c", None),
    ]

"""T17: monthly granularity for /api/trends/daily — same fold, same unpriced
rule, only the bucket key changes; the default (day) behaves exactly as before.
"""

import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from zlens.api.app import create_app

_DAY_A = "2026-07-31"  # July
_DAY_B = "2026-08-01"  # August, one day later — the month boundary


def _ms(day: str) -> int:
    dt = datetime.fromisoformat(f"{day}T12:00:00").astimezone()
    return int(dt.timestamp() * 1000)


_ROWS = [
    # priced channel: model-a, ¥1/M input
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
        "input_tokens": 2_000_000,
        "computed_total_tokens": 2_000_000,
    },
    # unpriced channel on the August day only
    {
        "provider_id": "chan-b",
        "model_id": "model-b",
        "started_at": _ms(_DAY_B),
        "input_tokens": 500_000,
        "computed_total_tokens": 500_000,
    },
]

_PRICES = {"zcode|chan-a|model-a": {"input": 1.0, "output": 0.0}}


@pytest.fixture
def client(make_settings, tmp_path):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps({"version": 1, "models": _PRICES}), encoding="utf-8")
    return TestClient(create_app(make_settings(rows=_ROWS, pricing_path=pricing_path)))


def test_default_granularity_is_day_and_unchanged(client):
    body = client.get("/api/trends/daily").json()

    assert body["granularity"] == "day"
    assert [d["day"] for d in body["days"]] == [_DAY_A, _DAY_B]


def test_monthly_buckets_by_year_month(client):
    body = client.get("/api/trends/daily", params={"granularity": "month"}).json()

    assert body["granularity"] == "month"
    assert [d["day"] for d in body["days"]] == ["2026-07", "2026-08"]
    july, august = body["days"]
    assert july["total_tokens"] == 1_000_000
    assert august["total_tokens"] == 2_500_000


def test_one_unpriced_day_poisons_its_whole_month_cost(client):
    body = client.get("/api/trends/daily", params={"granularity": "month"}).json()

    by_month = {d["day"]: d["estimated_cost"] for d in body["days"]}
    assert by_month["2026-07"] == 1.0  # fully priced: sum of its days
    assert by_month["2026-08"] is None  # one unpriced channel → null, not partial


def test_month_sums_equal_day_sums(client):
    day = client.get("/api/trends/daily").json()
    month = client.get("/api/trends/daily", params={"granularity": "month"}).json()

    for field in ("request_count", "input_tokens", "output_tokens", "total_tokens"):
        assert sum(d[field] for d in day["days"]) == sum(d[field] for d in month["days"])


def test_monthly_combines_with_window(client):
    body = client.get(
        "/api/trends/daily",
        params={"granularity": "month", "start": "2026-08-01", "end": "2026-08-31"},
    ).json()

    assert [d["day"] for d in body["days"]] == ["2026-08"]
    assert body["days"][0]["total_tokens"] == 2_500_000


def test_invalid_granularity_is_422(client):
    response = client.get("/api/trends/daily", params={"granularity": "week"})

    assert response.status_code == 422

"""T15: date-window pushdown (closed local-day interval) on the four windowed
endpoints. Default (no params) must behave exactly like before; the window is
cut inside each adapter, never by filtering full result sets at the API layer.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from zlens.api.app import create_app

_DAY_A = "2026-08-01"  # two channels: model-a 1000 tok, model-b 500 tok
_DAY_B = "2026-08-20"  # one channel: model-a 3000 tok


def _ms(day: str) -> int:
    """Local-noon ms for an ISO day: safely inside the local day cut whatever the tz."""
    dt = datetime.fromisoformat(f"{day}T12:00:00").astimezone()
    return int(dt.timestamp() * 1000)


_ROWS = [
    {
        "provider_id": "chan-a",
        "model_id": "model-a",
        "started_at": _ms(_DAY_A),
        "computed_total_tokens": 1000,
    },
    {
        "provider_id": "chan-b",
        "model_id": "model-b",
        "started_at": _ms(_DAY_A),
        "computed_total_tokens": 500,
    },
    {
        "provider_id": "chan-a",
        "model_id": "model-a",
        "started_at": _ms(_DAY_B),
        "computed_total_tokens": 3000,
    },
]

_MINIMAX = [
    {"model": "model-a", "events": [{"ms": _ms(_DAY_A), "total": 700, "input": 700, "output": 0}]},
    {"model": "model-b", "events": [{"ms": _ms(_DAY_A), "total": 300, "input": 300, "output": 0}]},
    {
        "model": "model-a",
        "events": [{"ms": _ms(_DAY_B), "total": 3000, "input": 3000, "output": 0}],
    },
]


def _opencode_message(msg_id: str, day: str, total: int) -> dict:
    return {
        "id": msg_id,
        "session_id": "s1",
        "created": _ms(day),
        "data": {
            "role": "assistant",
            "providerID": "opencode",
            "modelID": "model-a",
            "tokens": {"total": total, "input": total, "output": 0},
            "time": {"created": _ms(day)},
        },
    }


@pytest.fixture
def client(make_settings):
    """Zcode-only app so multi-source sums stay attributable to one adapter."""
    return TestClient(create_app(make_settings(rows=_ROWS)))


@pytest.fixture
def minimax_client(make_settings):
    return TestClient(create_app(make_settings(minimax=_MINIMAX)))


@pytest.fixture
def opencode_client(make_settings):
    return TestClient(
        create_app(
            make_settings(
                opencode=[
                    _opencode_message("a1", _DAY_A, 1000),
                    _opencode_message("a2", _DAY_B, 3000),
                ]
            )
        )
    )


def test_windowed_total_equals_sum_of_that_days_daily(client):
    body = client.get("/api/overview", params={"start": _DAY_A, "end": _DAY_A}).json()
    assert body["total_tokens"] == 1500
    assert body["request_count"] == 2

    daily = client.get("/api/trends/daily", params={"start": _DAY_A, "end": _DAY_A}).json()
    assert sum(d["total_tokens"] for d in daily["days"] if d["day"] == _DAY_A) == 1500


def test_no_params_matches_window_covering_everything(client):
    plain = client.get("/api/overview").json()
    covered = client.get(
        "/api/overview", params={"start": "2026-01-01", "end": "2026-12-31"}
    ).json()
    assert plain["total_tokens"] == covered["total_tokens"] == 4500
    assert plain["request_count"] == covered["request_count"] == 3
    # by_model aggregates per channel over the window: model-a appears on both
    # days but stays one row.
    assert len(plain["by_model"]) == len(covered["by_model"]) == 2
    totals = {m["model_id"]: m["total_tokens"] for m in plain["by_model"]}
    assert totals == {"model-a": 4000, "model-b": 500}


def test_empty_window_returns_zeros_and_empty_by_model(client):
    response = client.get("/api/overview", params={"start": "2026-01-01", "end": "2026-01-02"})

    assert response.status_code == 200
    body = response.json()
    assert body["request_count"] == 0
    assert body["total_tokens"] == 0
    assert body["by_model"] == []


def test_single_day_window(client):
    body = client.get("/api/overview", params={"start": _DAY_B, "end": _DAY_B}).json()
    assert body["total_tokens"] == 3000
    assert [m["model_id"] for m in body["by_model"]] == ["model-a"]


def test_window_bounds_are_inclusive(client):
    first = client.get("/api/overview", params={"start": _DAY_A, "end": _DAY_A}).json()
    assert first["total_tokens"] == 1500
    last = client.get("/api/overview", params={"start": _DAY_B, "end": _DAY_B}).json()
    assert last["total_tokens"] == 3000
    middle_gap = client.get(
        "/api/overview", params={"start": "2026-08-02", "end": "2026-08-19"}
    ).json()
    assert middle_gap["total_tokens"] == 0


def test_open_ended_window_keeps_unbounded_side(client):
    only_start = client.get("/api/overview", params={"start": _DAY_B}).json()
    assert only_start["total_tokens"] == 3000
    only_end = client.get("/api/overview", params={"end": _DAY_A}).json()
    assert only_end["total_tokens"] == 1500


def test_start_after_end_is_422(client):
    response = client.get("/api/overview", params={"start": _DAY_B, "end": _DAY_A})

    assert response.status_code == 422
    assert "start" in response.json()["detail"]


def test_malformed_date_is_422(client):
    response = client.get("/api/overview", params={"start": "08/01/2026"})

    assert response.status_code == 422


def test_meta_reflects_window(client):
    plain = client.get("/api/meta").json()
    assert plain["request_count"] == 3
    first = datetime.fromisoformat(plain["first_request_at"])
    last = datetime.fromisoformat(plain["last_request_at"])
    assert first.date().isoformat() == _DAY_A
    assert last.date().isoformat() == _DAY_B

    windowed = client.get("/api/meta", params={"start": _DAY_B, "end": _DAY_B}).json()
    assert windowed["request_count"] == 1
    assert datetime.fromisoformat(windowed["first_request_at"]).date().isoformat() == _DAY_B
    assert windowed["last_request_at"] == windowed["first_request_at"]


def test_models_ranking_honors_window(client):
    plain = client.get("/api/models").json()
    assert sum(m["total_tokens"] for m in plain["models"]) == 4500

    windowed = client.get("/api/models", params={"start": _DAY_A, "end": _DAY_A}).json()
    assert {m["model_id"] for m in windowed["models"]} == {"model-a", "model-b"}
    assert sum(m["total_tokens"] for m in windowed["models"]) == 1500


def test_minimax_window_is_cut_at_load(minimax_client):
    body = minimax_client.get(
        "/api/overview", params={"start": _DAY_B, "end": _DAY_B, "source": "minimax"}
    ).json()
    assert body["total_tokens"] == 3000


def test_opencode_window_is_pushed_into_sql(opencode_client):
    body = opencode_client.get(
        "/api/overview", params={"start": _DAY_A, "end": _DAY_A, "source": "opencode"}
    ).json()
    assert body["total_tokens"] == 1000


@pytest.mark.live
def test_live_window_smoke():
    """On the real db: a 7-day window covers no more requests than the full
    history, and its daily series sums back to the windowed total."""
    from zlens.core.config import load_settings

    settings = load_settings()
    if not settings.db_path.exists():
        pytest.skip("real ZCode database not present on this machine")
    client = TestClient(create_app(settings))

    full = client.get("/api/overview").json()
    end = datetime.now().astimezone().date()
    start = end - timedelta(days=6)
    params = {"start": start.isoformat(), "end": end.isoformat()}
    windowed = client.get("/api/overview", params=params).json()

    assert windowed["request_count"] <= full["request_count"]
    daily = client.get("/api/trends/daily", params=params).json()
    assert sum(d["total_tokens"] for d in daily["days"]) == windowed["total_tokens"]

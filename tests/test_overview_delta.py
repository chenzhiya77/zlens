"""T16: period-over-period delta against the previous equal-length window.

The previous window must be fully inside the data range AND non-empty, or the
delta disappears entirely — missing history must not render as "+300%".
"""

import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from zlens.api.app import create_app

# window W  = 08-11 .. 08-20 (current), previous P = 08-01 .. 08-10
_W_START, _W_END = "2026-08-11", "2026-08-20"


def _ms(day: str) -> int:
    dt = datetime.fromisoformat(f"{day}T12:00:00").astimezone()
    return int(dt.timestamp() * 1000)


def _row(day: str, tokens: int, provider: str = "chan-a", model: str = "model-a") -> dict:
    return {
        "provider_id": provider,
        "model_id": model,
        "started_at": _ms(day),
        "input_tokens": tokens,
        "computed_total_tokens": tokens,
    }


_PRICES = {"zcode|chan-a|model-a": {"input": 1.0, "output": 0.0}}


def _client(make_settings, tmp_path, rows, prices=None):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps({"version": 1, "models": prices or _PRICES}), encoding="utf-8"
    )
    return TestClient(create_app(make_settings(rows=rows, pricing_path=pricing_path)))


@pytest.fixture
def client(make_settings, tmp_path):
    """Reference shape: data starts on 08-01 (the previous window's first day),
    so the previous window is complete and populated."""
    return _client(
        make_settings,
        tmp_path,
        [_row("2026-08-01", 1_000_000), _row("2026-08-15", 3_000_000)],
    )


def test_delta_with_complete_previous_window(client):
    body = client.get("/api/overview", params={"start": _W_START, "end": _W_END}).json()

    assert body["delta"]["request_count"] == {"previous": 1, "change_rate": 0.0}
    assert body["delta"]["estimated_cost"] == {"previous": 1.0, "change_rate": 2.0}


def test_partial_previous_window_is_null_not_a_fake_spike(make_settings, tmp_path):
    """Data starts on 08-05, inside the previous window: the days before it aren't
    zero usage, they are no tool at all — the window is incomplete, so no delta."""
    client = _client(
        make_settings, tmp_path, [_row("2026-08-05", 1_000_000), _row("2026-08-15", 3_000_000)]
    )

    body = client.get("/api/overview", params={"start": _W_START, "end": _W_END}).json()

    assert body["delta"] is None


def test_fully_empty_previous_window_is_null(make_settings, tmp_path):
    """Completeness holds (data starts 07-20, before the previous window) but the
    previous stretch itself holds no requests: nothing to compare → no delta,
    not a "previous=0" figure dressed up as a measurement."""
    client = _client(
        make_settings, tmp_path, [_row("2026-07-20", 100_000), _row("2026-08-15", 3_000_000)]
    )

    body = client.get("/api/overview", params={"start": _W_START, "end": _W_END}).json()

    assert body["delta"] is None


def test_unpriced_side_gives_previous_but_no_change_rate(make_settings, tmp_path):
    """model-b is unpriced in the current window only: cost previous still ships,
    change_rate is null — unknown is not "no change"."""
    rows = [
        _row("2026-08-01", 1_000_000),
        _row("2026-08-15", 3_000_000),
        _row("2026-08-16", 500_000, provider="chan-b", model="model-b"),
    ]
    client = _client(make_settings, tmp_path, rows)

    body = client.get("/api/overview", params={"start": _W_START, "end": _W_END}).json()

    assert body["estimated_cost"] is None  # current period has an unpriced channel
    assert body["delta"]["request_count"] == {"previous": 1, "change_rate": 1.0}
    assert body["delta"]["estimated_cost"] == {"previous": 1.0, "change_rate": None}


def test_open_and_default_windows_have_no_delta(make_settings, tmp_path):
    client = _client(make_settings, tmp_path, [_row("2026-08-01", 1_000_000)])

    assert client.get("/api/overview").json()["delta"] is None  # 全部
    only_start = client.get("/api/overview", params={"start": _W_START}).json()
    assert only_start["delta"] is None  # unbounded side: no equal-length shift


def test_zero_previous_cost_gives_null_rate_not_infinity(make_settings, tmp_path):
    """A fully free (priced at 0) previous period: previous ships as 0.0 while
    change_rate must be null, never Infinity."""
    free = {"zcode|chan-a|model-a": {"input": 0.0, "output": 0.0}}
    client = _client(
        make_settings,
        tmp_path,
        [_row("2026-08-01", 1_000_000), _row("2026-08-15", 1_000_000)],
        prices=free,
    )

    body = client.get("/api/overview", params={"start": _W_START, "end": _W_END}).json()

    assert body["delta"]["estimated_cost"] == {"previous": 0.0, "change_rate": None}

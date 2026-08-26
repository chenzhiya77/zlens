import json

from fastapi.testclient import TestClient

from zlens.api.app import create_app
from zlens.core.config import Settings

_ROWS = [
    # provider, model, started_at, input, output, reasoning, cache_write, cache_read, total
    ("p", "priced", 1, 1_000_000, 100_000, 0, 200_000, 2_000_000, 3_300_000),
    ("p", "unpriced", 2, 500_000, 50_000, 0, 0, 0, 550_000),
]

_PRICES = {"priced": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75}}
# (1e6*3 + 1e5*15 + 2e6*0.3 + 2e5*3.75) / 1e6
_PRICED_COST = 5.85


def _client(make_db, rows, tmp_path, prices=None, raw=None):
    pricing_path = tmp_path / "pricing.json"
    if raw is not None:
        pricing_path.write_text(raw, encoding="utf-8")
    elif prices is not None:
        pricing_path.write_text(json.dumps({"version": 1, "models": prices}), encoding="utf-8")
    app = create_app(Settings(db_path=make_db(rows), pricing_path=pricing_path))
    return TestClient(app)


def test_cost_computed_for_fully_priced_models(make_db, tmp_path):
    rows = [_ROWS[0]]
    client = _client(make_db, rows, tmp_path, prices=_PRICES)

    body = client.get("/api/overview").json()

    assert body["estimated_cost_usd"] == _PRICED_COST
    assert body["by_model"][0]["estimated_cost_usd"] == _PRICED_COST
    assert client.get("/api/meta").json()["unpriced_models"] == []


def test_unpriced_model_stays_null_and_total_stays_null(make_db, tmp_path):
    client = _client(make_db, _ROWS, tmp_path, prices=_PRICES)

    body = client.get("/api/overview").json()

    costs = {m["model_id"]: m["estimated_cost_usd"] for m in body["by_model"]}
    assert costs == {"priced": _PRICED_COST, "unpriced": None}
    assert body["estimated_cost_usd"] is None
    assert client.get("/api/meta").json()["unpriced_models"] == ["unpriced"]


def test_missing_cache_tiers_default_to_zero(make_db, tmp_path):
    client = _client(
        make_db,
        [_ROWS[0]],
        tmp_path,
        prices={"priced": {"input": 1.0, "output": 2.0}},
    )

    body = client.get("/api/overview").json()

    # (1e6*1 + 1e5*2) / 1e6 — cache tiers absent from the price entry cost nothing.
    assert body["by_model"][0]["estimated_cost_usd"] == 1.2


def test_price_edit_takes_effect_without_restart(make_db, tmp_path):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps({"version": 1, "models": _PRICES}), encoding="utf-8")
    client = TestClient(
        create_app(Settings(db_path=make_db([_ROWS[0]]), pricing_path=pricing_path))
    )

    assert client.get("/api/overview").json()["estimated_cost_usd"] == _PRICED_COST

    pricing_path.write_text(
        json.dumps({"version": 1, "models": {"priced": {**_PRICES["priced"], "input": 6.0}}}),
        encoding="utf-8",
    )

    # (6e6 + 1.5e6 + 0.6e6 + 0.75e6) / 1e6
    assert client.get("/api/overview").json()["estimated_cost_usd"] == 8.85


def test_malformed_pricing_file_degrades_to_unpriced(make_db, tmp_path):
    client = _client(make_db, [_ROWS[0]], tmp_path, raw="{not json")

    response = client.get("/api/overview")

    assert response.status_code == 200
    assert response.json()["estimated_cost_usd"] is None
    assert response.json()["by_model"][0]["estimated_cost_usd"] is None

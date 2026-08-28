"""Price-table read/write endpoints: load, save, validation, hot effect.

Keys are per-channel triples 'source|provider_id|model_id' (see model_key) — one
row per channel, so two channels serving the same model id keep separate prices.
"""

_KEY = "zcode|unknown|demo-model"


def _table(extra=None):
    return {
        "version": 1,
        "models": {
            _KEY: {
                "input": 3.0,
                "output": 15.0,
                "cache_read": 0.3,
                "cache_write": 3.75,
            },
            **(extra or {}),
        },
    }


def test_pricing_get_returns_empty_table_by_default(client_factory):
    body = (
        client_factory(rows=[{"model_id": "m1", "computed_total_tokens": 10}])
        .get("/api/pricing")
        .json()
    )

    assert body["version"] == 1
    assert body["models"] == {}


def test_pricing_put_writes_file_and_takes_effect_on_overview(client_factory, tmp_path):
    pricing_path = tmp_path / "pricing.json"
    client = client_factory(
        rows=[
            {
                "model_id": "demo-model",
                "input_tokens": 1_000_000,
                "computed_total_tokens": 1_000_000,
            }
        ],
        pricing_path=pricing_path,
    )

    saved = client.put("/api/pricing", json=_table()).json()

    assert saved["models"][_KEY]["input"] == 3.0
    assert pricing_path.exists()
    overview = client.get("/api/overview").json()
    assert overview["estimated_cost"] == 3.0
    assert overview["by_model"][0]["estimated_cost"] == 3.0


def test_pricing_put_rejects_negative_price(client_factory, tmp_path):
    client = client_factory(rows=[], pricing_path=tmp_path / "pricing.json")

    response = client.put(
        "/api/pricing",
        json={
            "version": 1,
            "models": {
                "zcode|unknown|m": {
                    "input": -1,
                    "output": 15.0,
                    "cache_read": 0.1,
                    "cache_write": 0,
                }
            },
        },
    )

    assert response.status_code == 422


def test_pricing_put_rejects_legacy_bare_model_id(client_factory, tmp_path):
    """A bare model id can never match a usage row: rejecting it beats silent zero cost."""
    client = client_factory(rows=[], pricing_path=tmp_path / "pricing.json")

    response = client.put("/api/pricing", json=_table({"demo-model": {"input": 1, "output": 2}}))

    assert response.status_code == 422


def test_pricing_put_rejects_incomplete_channel_key(client_factory, tmp_path):
    client = client_factory(rows=[], pricing_path=tmp_path / "pricing.json")

    response = client.put(
        "/api/pricing",
        json=_table({"zcode||demo-model": {"input": 1, "output": 2}}),
    )

    assert response.status_code == 422


def test_pricing_put_round_trips_fx(client_factory, tmp_path):
    client = client_factory(rows=[], pricing_path=tmp_path / "pricing.json")

    saved = client.put(
        "/api/pricing",
        json={
            "version": 1,
            "fx_usd_cny": 7.2,
            "models": {_KEY: {"input": 3.0, "output": 15.0}},
        },
    ).json()

    assert saved["fx_usd_cny"] == 7.2
    assert saved["models"][_KEY]["input"] == 3.0


def test_pricing_put_rejects_non_positive_fx(client_factory, tmp_path):
    """A zero or negative rate would fold every $ entry into a nonsense number."""
    client = client_factory(rows=[], pricing_path=tmp_path / "pricing.json")

    response = client.put(
        "/api/pricing",
        json={
            "version": 1,
            "fx_usd_cny": 0,
            "models": {_KEY: {"input": 3.0, "output": 15.0}},
        },
    )

    assert response.status_code == 422


def test_pricing_put_round_trips_buyout_amount(client_factory, tmp_path):
    """A plan amount belongs to its channel; a row without one stays null, not 0."""
    client = client_factory(rows=[], pricing_path=tmp_path / "pricing.json")

    saved = client.put(
        "/api/pricing",
        json={
            "version": 1,
            "models": {
                _KEY: {"input": 0, "output": 0, "buyout_amount": 299.0},
                "zcode|chan-b|other": {"input": 1.0, "output": 2.0},
            },
        },
    ).json()

    assert saved["models"][_KEY]["buyout_amount"] == 299.0
    assert saved["models"]["zcode|chan-b|other"]["buyout_amount"] is None


def test_pricing_put_rejects_negative_buyout_amount(client_factory, tmp_path):
    client = client_factory(rows=[], pricing_path=tmp_path / "pricing.json")

    response = client.put(
        "/api/pricing",
        json={
            "version": 1,
            "models": {_KEY: {"input": 1.0, "output": 2.0, "buyout_amount": -1}},
        },
    )

    assert response.status_code == 422

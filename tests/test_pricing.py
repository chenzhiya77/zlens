"""Price-table read/write endpoints: load, save, validation, hot effect."""


def _table(extra=None):
    return {
        "version": 1,
        "models": {
            "demo-model": {
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

    assert saved["models"]["demo-model"]["input"] == 3.0
    assert pricing_path.exists()
    overview = client.get("/api/overview").json()
    assert overview["estimated_cost_usd"] == 3.0
    assert overview["by_model"][0]["estimated_cost_usd"] == 3.0


def test_pricing_put_rejects_negative_price(client_factory, tmp_path):
    client = client_factory(rows=[], pricing_path=tmp_path / "pricing.json")

    response = client.put(
        "/api/pricing",
        json={
            "version": 1,
            "models": {"m": {"input": -1, "output": 15.0, "cache_read": 0.1, "cache_write": 0}},
        },
    )

    assert response.status_code == 422


def test_pricing_put_rejects_empty_model_id(client_factory, tmp_path):
    client = client_factory(rows=[], pricing_path=tmp_path / "pricing.json")

    response = client.put(
        "/api/pricing",
        json={
            "version": 1,
            "models": {"": {"input": 1, "output": 2, "cache_read": 0.1, "cache_write": 0}},
        },
    )

    assert response.status_code == 422

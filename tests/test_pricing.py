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


def test_put_credit_prices_sanitized_and_version_bumped(client_factory, make_workbuddy):
    """积分单价是 v2 形状:录入任一条把文件升到 v2;非法条目被消毒器丢弃
    (降级而非报错),合法条目落库并在 GET 里原样返回。"""
    client = client_factory(
        rows=[{"model_id": "m1", "computed_total_tokens": 1}],
        workbuddy=[
            {
                "project_slug": "e--app-proj",
                "session_id": "s1",
                "records": [],
            }
        ],
    )
    table = {
        "version": 1,
        "models": {},
        "credit_prices": {
            "workbuddy|plan": {"cny_per_credit": 0.0495, "note": "¥99/月 ÷ 2000"},
            "bogus": {"cny_per_credit": 1.0},  # 缺 basis → 丢弃
            "workbuddy|pack": {"cny_per_credit": -1},  # 非正数 → 丢弃
        },
    }
    body = client.put("/api/pricing", json=table).json()
    assert body["version"] == 2
    assert set(body["credit_prices"]) == {"workbuddy|plan"}
    assert body["credit_prices"]["workbuddy|plan"]["note"] == "¥99/月 ÷ 2000"
    stored = client.get("/api/pricing").json()
    assert stored["credit_prices"]["workbuddy|plan"]["cny_per_credit"] == 0.0495


def test_put_without_credit_prices_keeps_v1(client_factory):
    client = client_factory(rows=[{"model_id": "m1", "computed_total_tokens": 1}])
    body = client.put("/api/pricing", json=_table()).json()
    assert body["version"] == 1
    assert body["credit_prices"] == {}


def test_unpriced_credits_clears_after_credit_price_recorded(client_factory, make_workbuddy):
    """meta.unpriced_credits 是积分侧的待补价:录入任一 basis 单价即清出。"""
    client = client_factory(
        rows=[{"model_id": "m1", "computed_total_tokens": 1}],
        workbuddy=[
            {
                "project_slug": "e--app-proj",
                "session_id": "s1",
                "records": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "timestamp": 1788000000000,
                        "cwd": "E:/app/proj",
                        "sessionId": "s1",
                        "id": "m1",
                        "providerData": {
                            "messageId": "m1",
                            "model": "glm-5.2",
                            "requestModelId": "auto",
                            "rawUsage": {
                                "prompt_tokens": 10,
                                "completion_tokens": 5,
                                "total_tokens": 15,
                                "credit": 1.0,
                            },
                        },
                    }
                ],
            }
        ],
    )
    before = client.get("/api/meta").json()
    assert before["credit_reporting_sources"] == ["workbuddy"]
    assert before["unpriced_credits"] == ["workbuddy"]

    client.put(
        "/api/pricing",
        json={"version": 2, "models": {}, "credit_prices": {}},  # 空 credit_prices 不清账
    )
    assert client.get("/api/meta").json()["unpriced_credits"] == ["workbuddy"]

    client.put(
        "/api/pricing",
        json={
            "version": 2,
            "models": {},
            "credit_prices": {"workbuddy|plan": {"cny_per_credit": 0.0495}},
        },
    )
    after = client.get("/api/meta").json()
    assert after["unpriced_credits"] == []
    overview = client.get("/api/overview", params={"source": "workbuddy"}).json()
    assert overview["credit_value_cny"]["plan"] == 0.0495

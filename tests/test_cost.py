import json

from fastapi.testclient import TestClient

from zlens.api.app import create_app
from zlens.core.config import Settings

_ROWS = [
    {
        "provider_id": "chan-official",
        "model_id": "priced",
        # Nested like the real db: the 1M billable input sits *on top of* 2M cache
        # read + 0.2M cache write inside input_tokens, and total is input + output.
        "input_tokens": 3_200_000,
        "output_tokens": 100_000,
        "cache_creation_input_tokens": 200_000,
        "cache_read_input_tokens": 2_000_000,
        "computed_total_tokens": 3_300_000,
    },
    {
        "provider_id": "chan-reseller",
        "model_id": "unpriced",
        "input_tokens": 500_000,
        "output_tokens": 50_000,
        "computed_total_tokens": 550_000,
    },
]

# Price keys are per-channel triples 'source|provider_id|model_id' (see model_key):
# the same model served by another channel is a separate row with a separate price.
_KEY = "zcode|chan-official|priced"
_PRICES = {
    _KEY: {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write": 3.75,
    }
}
# (1e6*3 + 1e5*15 + 2e6*0.3 + 2e5*3.75) / 1e6
_PRICED_COST = 5.85


def _client(make_db, rows, tmp_path, prices=None, raw=None, fx=None):
    pricing_path = tmp_path / "pricing.json"
    if raw is not None:
        pricing_path.write_text(raw, encoding="utf-8")
    elif prices is not None:
        table = {"version": 1, "models": prices}
        if fx is not None:
            table["fx_usd_cny"] = fx
        pricing_path.write_text(json.dumps(table), encoding="utf-8")
    app = create_app(
        Settings(
            db_path=make_db(rows),
            pricing_path=pricing_path,
            minimax_sessions_dir=tmp_path / "minimax-missing",
            opencode_db_path=tmp_path / "opencode-missing.db",
        )
    )
    return TestClient(app)


def _kimi_rows():
    """The same model id served through two channels, 1M input tokens each."""
    return [
        {
            "provider_id": provider_id,
            "model_id": "kimi-k3",
            "input_tokens": 1_000_000,
            "computed_total_tokens": 1_000_000,
        }
        for provider_id in ("chan-a", "chan-b")
    ]


def test_cost_computed_for_fully_priced_models(make_db, tmp_path):
    rows = [_ROWS[0]]
    client = _client(make_db, rows, tmp_path, prices=_PRICES)

    body = client.get("/api/overview").json()

    assert body["estimated_cost"] == _PRICED_COST
    assert body["by_model"][0]["estimated_cost"] == _PRICED_COST
    assert client.get("/api/meta").json()["unpriced_models"] == []


def test_cached_prefix_is_not_charged_twice(make_db, tmp_path):
    """The whole prompt was served from cache: those tokens are already inside
    input_tokens, so they must cost the cache-read tier and nothing more."""
    rows = [
        {
            "provider_id": "chan-official",
            "model_id": "priced",
            "input_tokens": 1_000_000,
            "output_tokens": 0,
            "cache_read_input_tokens": 1_000_000,
            "computed_total_tokens": 1_000_000,
        }
    ]
    client = _client(make_db, rows, tmp_path, prices=_PRICES)

    body = client.get("/api/overview").json()

    assert body["input_tokens"] == 0
    assert body["estimated_cost"] == 0.3


def test_cache_beyond_input_clamps_instead_of_going_negative(make_db, tmp_path):
    """One malformed record must not subtract another row's billable input away."""
    rows = [
        {
            "provider_id": "chan-official",
            "model_id": "priced",
            "input_tokens": 500,
            "output_tokens": 0,
            "cache_read_input_tokens": 1_000,
            "computed_total_tokens": 1_500,
        }
    ]
    client = _client(make_db, rows, tmp_path, prices=_PRICES)

    body = client.get("/api/overview").json()

    assert body["input_tokens"] == 0
    assert body["estimated_cost"] == 0.0003


def test_unpriced_row_stays_null_total_sums_priced_only(make_db, tmp_path):
    client = _client(make_db, _ROWS, tmp_path, prices=_PRICES)

    body = client.get("/api/overview").json()

    costs = {m["model_id"]: m["estimated_cost"] for m in body["by_model"]}
    assert costs == {"priced": _PRICED_COST, "unpriced": None}
    assert body["estimated_cost"] == _PRICED_COST  # unpriced row counts ¥0
    assert client.get("/api/meta").json()["unpriced_models"] == ["zcode|chan-reseller|unpriced"]


def test_same_model_on_two_channels_is_priced_per_channel(make_db, tmp_path):
    client = _client(
        make_db,
        _kimi_rows(),
        tmp_path,
        prices={
            "zcode|chan-a|kimi-k3": {"input": 3.0, "output": 0.0},
            "zcode|chan-b|kimi-k3": {"input": 1.0, "output": 0.0},
        },
    )

    body = client.get("/api/overview").json()

    costs = {m["provider_id"]: m["estimated_cost"] for m in body["by_model"]}
    assert costs == {"chan-a": 3.0, "chan-b": 1.0}
    assert body["estimated_cost"] == 4.0


def test_price_never_leaks_between_channels_of_one_model(make_db, tmp_path):
    client = _client(
        make_db,
        _kimi_rows(),
        tmp_path,
        prices={"zcode|chan-a|kimi-k3": {"input": 3.0, "output": 0.0}},
    )

    body = client.get("/api/overview").json()

    costs = {m["provider_id"]: m["estimated_cost"] for m in body["by_model"]}
    assert costs == {"chan-a": 3.0, "chan-b": None}
    # Unpriced channel counts as ¥0: the total is the priced channel only.
    assert body["estimated_cost"] == 3.0
    assert client.get("/api/meta").json()["unpriced_models"] == ["zcode|chan-b|kimi-k3"]


def test_fx_rate_never_touches_costing(make_db, tmp_path):
    """fx_usd_cny is an entry-time aid; costing must ignore it completely."""
    client = _client(make_db, [_ROWS[0]], tmp_path, prices=_PRICES, fx=7.2)

    body = client.get("/api/overview").json()

    assert body["estimated_cost"] == _PRICED_COST


def test_missing_cache_tiers_default_to_zero(make_db, tmp_path):
    client = _client(
        make_db,
        [_ROWS[0]],
        tmp_path,
        prices={"zcode|chan-official|priced": {"input": 1.0, "output": 2.0}},
    )

    body = client.get("/api/overview").json()

    # (1e6*1 + 1e5*2) / 1e6 — cache tiers absent from the price entry cost nothing.
    assert body["by_model"][0]["estimated_cost"] == 1.2


def test_price_edit_takes_effect_without_restart(make_db, tmp_path):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps({"version": 1, "models": _PRICES}), encoding="utf-8")
    client = TestClient(
        create_app(
            Settings(
                db_path=make_db([_ROWS[0]]),
                pricing_path=pricing_path,
                minimax_sessions_dir=tmp_path / "minimax-missing",
                opencode_db_path=tmp_path / "opencode-missing.db",
            )
        )
    )

    assert client.get("/api/overview").json()["estimated_cost"] == _PRICED_COST

    pricing_path.write_text(
        json.dumps(
            {
                "version": 1,
                "models": {"zcode|chan-official|priced": {**_PRICES[_KEY], "input": 6.0}},
            }
        ),
        encoding="utf-8",
    )

    # (6e6 + 1.5e6 + 0.6e6 + 0.75e6) / 1e6
    assert client.get("/api/overview").json()["estimated_cost"] == 8.85


def test_malformed_pricing_file_degrades_to_unpriced(make_db, tmp_path):
    client = _client(make_db, [_ROWS[0]], tmp_path, raw="{not json")

    response = client.get("/api/overview")

    assert response.status_code == 200
    assert response.json()["estimated_cost"] == 0  # nothing priced: nothing to sum
    assert response.json()["by_model"][0]["estimated_cost"] is None


def test_stale_currency_field_in_pricing_file_is_ignored(make_db, tmp_path):
    """An older build stored a per-row `currency`; costing is CNY-only and must load
    those files unchanged rather than choking on the key it no longer declares."""
    stale = json.dumps(
        {
            "version": 1,
            "models": {_KEY: {**_PRICES[_KEY], "currency": "usd"}},
            "fx_usd_cny": 7.2,
        }
    )
    client = _client(make_db, [_ROWS[0]], tmp_path, raw=stale)

    assert client.get("/api/overview").json()["estimated_cost"] == _PRICED_COST


def test_buyout_total_counts_paid_amounts_not_usage(make_db, tmp_path):
    """Money already paid is its own figure: rows without an amount contribute
    nothing, a plan channel that never ran still counts, and an unpriced channel
    counts ¥0 toward the consumption total but cannot make paid money unknown."""
    client = _client(
        make_db,
        _ROWS,  # second channel stays unpriced -> it counts ¥0 toward consumption
        tmp_path,
        prices={
            _KEY: {**_PRICES[_KEY], "buyout_amount": 299.0},
            "zcode|chan-plan|no-usage": {"input": 0.0, "output": 0.0, "buyout_amount": 60.0},
        },
    )

    body = client.get("/api/overview").json()

    assert body["estimated_cost"] == _PRICED_COST
    assert body["buyout_total"] == 359.0


def test_buyout_amount_never_enters_the_per_token_cost(make_db, tmp_path):
    client = _client(
        make_db,
        [_ROWS[0]],
        tmp_path,
        prices={_KEY: {**_PRICES[_KEY], "buyout_amount": 299.0}},
    )

    body = client.get("/api/overview").json()

    assert body["estimated_cost"] == _PRICED_COST
    assert body["by_model"][0]["estimated_cost"] == _PRICED_COST
    assert body["buyout_total"] == 299.0

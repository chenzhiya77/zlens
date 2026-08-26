import json
from datetime import UTC, datetime, timedelta

from zlens.core.cost import PriceTable, fold_daily

_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=UTC)

_MS_DAY1_A = 1_700_000_000_000  # local day D1
_MS_DAY1_B = 1_700_005_000_000  # local day D1 (later request)
_MS_DAY2 = 1_700_100_000_000  # local day D2


def _local_day(ms: int) -> str:
    return (_EPOCH_UTC + timedelta(milliseconds=ms)).astimezone().strftime("%Y-%m-%d")


def _rows():
    return [
        {
            "model_id": "alpha",
            "started_at": _MS_DAY1_A,
            "input_tokens": 100,
            "output_tokens": 10,
            "cache_read_input_tokens": 1000,
            "computed_total_tokens": 1110,
        },
        {
            "model_id": "beta",
            "started_at": _MS_DAY1_B,
            "input_tokens": 200,
            "output_tokens": 20,
            "cache_read_input_tokens": 2000,
            "computed_total_tokens": 2220,
        },
        {
            "model_id": "alpha",
            "started_at": _MS_DAY2,
            "input_tokens": 300,
            "output_tokens": 30,
            "cache_read_input_tokens": 3000,
            "computed_total_tokens": 3330,
        },
    ]


def _pricing(tmp_path, prices):
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps({"version": 1, "models": prices}), encoding="utf-8")
    return path


def test_daily_trends_fold_and_cost_rule(client_factory, tmp_path):
    client = client_factory(_rows())
    table = PriceTable.load(_pricing(tmp_path, {"alpha": {"input": 3.0, "output": 0.0}}))
    body = fold_daily(client.app.state.source.daily_by_model(), table)

    assert [d.day for d in body.days] == sorted({_local_day(_MS_DAY1_A), _local_day(_MS_DAY2)})
    day1, day2 = body.days
    assert (day1.request_count, day1.input_tokens, day1.total_tokens) == (2, 300, 3330)
    assert (day2.request_count, day2.total_tokens) == (1, 3330)
    # Day 1 serves unpriced `beta` -> honest null; day 2 is alpha-only -> priced.
    assert day1.estimated_cost_usd is None
    assert day2.estimated_cost_usd == 0.0009

    assert [(r.day, r.model_id) for r in body.by_model] == [
        (_local_day(_MS_DAY1_A), "beta"),  # higher day-1 total ranks first
        (_local_day(_MS_DAY1_A), "alpha"),
        (_local_day(_MS_DAY2), "alpha"),
    ]
    assert body.by_model[0].estimated_cost_usd is None
    assert body.by_model[1].estimated_cost_usd == 0.0003


def test_daily_trends_via_api(client_factory):
    body = client_factory(_rows()).get("/api/trends/daily").json()

    assert len(body["days"]) == 2
    assert body["days"][0]["day"] == _local_day(_MS_DAY1_A)
    assert body["by_model"][0]["model_id"] == "beta"  # highest day-1 total first


def test_models_ranking_matches_overview_order(client_factory, tmp_path):
    client = client_factory(_rows())
    _pricing(tmp_path, {"alpha": {"input": 3.0, "output": 0.0}})

    ranking = client.get("/api/models").json()
    overview = client.get("/api/overview").json()

    assert [m["model_id"] for m in ranking["models"]] == ["alpha", "beta"]
    assert ranking["models"][0]["request_count"] == 2
    assert ranking["models"][0]["total_tokens"] == 4440
    assert [m["model_id"] for m in ranking["models"]] == [
        m["model_id"] for m in overview["by_model"]
    ]


def test_empty_database_yields_empty_trends_and_ranking(client_factory):
    client = client_factory([])

    assert client.get("/api/trends/daily").json() == {"days": [], "by_model": []}
    assert client.get("/api/models").json() == {"models": []}

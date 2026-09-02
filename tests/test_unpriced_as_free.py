"""未计价按 ¥0 计入(产品决策 2026-09-02):没有单价就当免费,聚合永远给出。

行级 `estimated_cost` 仍是 null——明细里的「—」是「还没定价」的标记,排序照旧
排最后;价格表「待补价」分组与 /api/meta 的 unpriced_models 照旧列出未计价渠道,
`meta` 的全量清单(含 0 token 的探路渠道)供编辑器播种补价行。
"""

import json

_MS_DAY1 = 1_700_000_000_000

_PRICED_ROW = {
    "provider_id": "chan-a",
    "model_id": "priced",
    "started_at": _MS_DAY1,
    "input_tokens": 1_000_000,
    "computed_total_tokens": 1_000_000,
}
# The request happened but nothing burned: token columns fall back to 0.
_PROBE_ROW = {
    "provider_id": "chan-b",
    "model_id": "mystery",
    "started_at": _MS_DAY1,
}
# A channel that actually burned tokens without a price: counts as ¥0.
_BUSY_UNPRICED_ROW = {
    "provider_id": "chan-b",
    "model_id": "busy",
    "started_at": _MS_DAY1,
    "input_tokens": 500_000,
    "computed_total_tokens": 500_000,
}
_PRICES = {"zcode|chan-a|priced": {"input": 2.0, "output": 0.0}}


def _client(client_factory, tmp_path, rows, sessions=()):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps({"version": 1, "models": _PRICES}), encoding="utf-8")
    return client_factory(rows=rows, sessions=sessions, pricing_path=pricing_path)


def test_unpriced_channels_count_zero_total_still_ships(client_factory, tmp_path):
    body = (
        _client(client_factory, tmp_path, [_PRICED_ROW, _PROBE_ROW, _BUSY_UNPRICED_ROW])
        .get("/api/overview")
        .json()
    )

    assert body["totals"]["estimated_cost"] == 2.0  # only the priced row converts
    assert body["totals"]["total_tokens"] == 1_500_000  # unpriced tokens still sum
    costs = {m["model_id"]: m["estimated_cost"] for m in body["by_model"]}
    assert costs == {"priced": 2.0, "mystery": None, "busy": None}  # rows keep the marker


def test_day_cost_sums_priced_only(client_factory, tmp_path):
    body = (
        _client(client_factory, tmp_path, [_PRICED_ROW, _BUSY_UNPRICED_ROW])
        .get("/api/trends/daily")
        .json()
    )

    assert len(body["days"]) == 1
    assert body["days"][0]["estimated_cost"] == 2.0


def test_project_cost_sums_priced_only(client_factory, tmp_path):
    rows = [
        _PRICED_ROW | {"session_id": "s1"},
        _BUSY_UNPRICED_ROW | {"session_id": "s1"},
    ]
    body = (
        _client(client_factory, tmp_path, rows, sessions=[("s1", "E:/work/proj", "T")])
        .get("/api/projects")
        .json()
    )

    assert body["projects"][0]["estimated_cost"] == 2.0


def test_meta_still_enumerates_unpriced_channels(client_factory, tmp_path):
    # The pricing editor needs the full enumeration (including the zero-token
    # probe) to seed a row the user can fill a price into.
    body = (
        _client(client_factory, tmp_path, [_PRICED_ROW, _PROBE_ROW, _BUSY_UNPRICED_ROW])
        .get("/api/meta")
        .json()
    )

    assert body["unpriced_models"] == ["zcode|chan-b|busy", "zcode|chan-b|mystery"]

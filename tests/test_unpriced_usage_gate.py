"""The unpriced gate blocks only on burned tokens.

A 0-token unpriced channel costs ¥0 under any unit price, so its missing price
hides nothing and must not null a computable total. Real case that prompted this:
one failed probe request through `zcode|builtin:zai|GLM-5.3-Flash` (1 request,
0 tokens) turned the whole overview into 未计价 although every token in the
window was priced.
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
_PRICES = {"zcode|chan-a|priced": {"input": 2.0, "output": 0.0}}


def _client(client_factory, tmp_path, rows, sessions=()):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps({"version": 1, "models": _PRICES}), encoding="utf-8")
    return client_factory(rows=rows, sessions=sessions, pricing_path=pricing_path)


def test_zero_token_probe_does_not_block_overview_total(client_factory, tmp_path):
    body = _client(client_factory, tmp_path, [_PRICED_ROW, _PROBE_ROW]).get("/api/overview").json()

    assert body["totals"]["estimated_cost"] == 2.0
    assert body["totals"]["total_tokens"] == 1_000_000
    probe = next(m for m in body["by_model"] if m["model_id"] == "mystery")
    assert (probe["request_count"], probe["total_tokens"]) == (1, 0)
    assert probe["estimated_cost"] is None  # the row itself stays tokens-only


def test_probe_with_tokens_still_blocks_total(client_factory, tmp_path):
    # Reverse assertion: the gate still fires when the unpriced channel burned
    # tokens — proves the zero-token test constrains the rule rather than passing
    # vacuously.
    probe = _PROBE_ROW | {"input_tokens": 500_000, "computed_total_tokens": 500_000}
    body = _client(client_factory, tmp_path, [_PRICED_ROW, probe]).get("/api/overview").json()

    assert body["totals"]["estimated_cost"] is None


def test_zero_token_probe_does_not_block_day_cost(client_factory, tmp_path):
    body = (
        _client(client_factory, tmp_path, [_PRICED_ROW, _PROBE_ROW]).get("/api/trends/daily").json()
    )

    assert len(body["days"]) == 1
    assert body["days"][0]["estimated_cost"] == 2.0


def test_zero_token_probe_does_not_block_project_cost(client_factory, tmp_path):
    rows = [_PRICED_ROW | {"session_id": "s1"}, _PROBE_ROW | {"session_id": "s1"}]
    body = (
        _client(client_factory, tmp_path, rows, sessions=[("s1", "E:/work/proj", "T")])
        .get("/api/projects")
        .json()
    )

    assert body["projects"][0]["estimated_cost"] == 2.0


def test_meta_still_enumerates_zero_token_unpriced_channels(client_factory, tmp_path):
    # The overview banner filters zero-usage channels out, but the pricing editor
    # needs the full enumeration to seed a row the user can fill a price into.
    body = _client(client_factory, tmp_path, [_PRICED_ROW, _PROBE_ROW]).get("/api/meta").json()

    assert body["unpriced_models"] == ["zcode|chan-b|mystery"]

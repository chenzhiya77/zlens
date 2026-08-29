"""T25: lock in zcode's per-row clamp — one malformed record (cached prefix
larger than the whole input) must contribute 0, never subtract from other rows.

The reverse assertion proves this file has teeth: on this fixture, the plausible
"refactor" of moving MAX outside SUM computes a *different* number, so breaking
the invariant turns this suite red instead of passing silently.
"""

import sqlite3

from zlens.sources.zcode import ZcodeSource

_GOOD_BIG = {
    "provider_id": "chan-a",
    "model_id": "m",
    "input_tokens": 1_000,
    "cache_read_input_tokens": 0,
    "cache_creation_input_tokens": 0,
    "computed_total_tokens": 1_000,
}
# normalized input 100 - 90 = 10
_GOOD_SMALL = {
    "provider_id": "chan-a",
    "model_id": "m",
    "input_tokens": 100,
    "cache_read_input_tokens": 90,
    "cache_creation_input_tokens": 0,
    "computed_total_tokens": 100,
}
# 100 - 400 = -300 raw → per-row clamp must cut it to 0
_DIRTY = {
    "provider_id": "chan-b",
    "model_id": "m",
    "input_tokens": 100,
    "cache_read_input_tokens": 400,
    "cache_creation_input_tokens": 0,
    "computed_total_tokens": 100,
}

_MIXED = [_GOOD_BIG, _GOOD_SMALL, _DIRTY]


def test_malformed_row_contributes_zero_and_never_offsets_good_rows(make_db):
    overview = ZcodeSource(make_db(_MIXED)).overview()

    assert overview.input_tokens == 1010  # 1000 + 10 + 0 — the -300 never lands


def test_clamp_is_per_channel_in_by_model(make_db):
    overview = ZcodeSource(make_db(_MIXED)).overview()

    inputs = {row.provider_id: row.input_tokens for row in overview.by_model}
    assert inputs == {"chan-a": 1010, "chan-b": 0}


def test_all_dirty_rows_yield_zero_without_raising(make_db):
    rows = [
        {
            "provider_id": "chan-b",
            "model_id": "m",
            "input_tokens": 100,
            "cache_read_input_tokens": 400,
            "cache_creation_input_tokens": 0,
            "computed_total_tokens": 100,
        },
        {
            "provider_id": "chan-b",
            "model_id": "m",
            "input_tokens": 0,
            "cache_read_input_tokens": 50,
            "cache_creation_input_tokens": 0,
            "computed_total_tokens": 0,
        },
    ]

    overview = ZcodeSource(make_db(rows)).overview()

    assert overview.input_tokens == 0
    assert overview.total_tokens == 100


def test_moving_max_outside_sum_would_change_the_result(make_db):
    """Reverse assertion: the plausible-looking 'optimization' computes 1000 here,
    not 1010 — so this suite genuinely constrains MAX living inside SUM."""
    db_path = make_db(_MIXED)
    con = sqlite3.connect(db_path)
    try:
        wrong = con.execute(
            "SELECT COALESCE(MAX("
            "  COALESCE(input_tokens, 0) - COALESCE(cache_read_input_tokens, 0)"
            "  - COALESCE(cache_creation_input_tokens, 0), 0), 0) FROM model_usage"
        ).fetchone()[0]
    finally:
        con.close()

    correct = ZcodeSource(db_path).overview().input_tokens
    assert correct == 1010
    assert wrong == 1000 and wrong != correct

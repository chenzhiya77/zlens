"""T21: cache_hit_rate = cache_read / (input + cache_read + cache_creation),
denominator 0 → null. Fixtures keep the real zcode nested shape: input_tokens
contains the cached prefix, exactly like the live db (方案 A: 分母含缓存写).
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from zlens.api.app import create_app

_DAY_A = "2026-08-01"
_DAY_B = "2026-08-20"


def _ms(day: str) -> int:
    dt = datetime.fromisoformat(f"{day}T12:00:00").astimezone()
    return int(dt.timestamp() * 1000)


# Nested like the real db: input_tokens 3.2M sits *on top of* 2M cache read +
# 0.2M cache write; normalized (billed) input is 1M → rate 2.0/3.2 = 0.625.
_NESTED_ROWS = [
    {
        "provider_id": "chan-official",
        "model_id": "priced",
        "started_at": _ms(_DAY_A),
        "input_tokens": 3_200_000,
        "output_tokens": 100_000,
        "cache_creation_input_tokens": 200_000,
        "cache_read_input_tokens": 2_000_000,
        "computed_total_tokens": 3_300_000,
    }
]


@pytest.fixture
def client(make_settings):
    return TestClient(create_app(make_settings(rows=_NESTED_ROWS)))


def test_overview_and_row_rate_on_nested_shape(client):
    body = client.get("/api/overview").json()

    assert body["cache_hit_rate"] == 0.625
    assert body["by_model"][0]["cache_hit_rate"] == 0.625


def test_zero_prompt_denominator_is_null_not_zero(make_settings):
    rows = [
        {
            "provider_id": "chan-x",
            "model_id": "idle",
            "started_at": _ms(_DAY_A),
            # a request whose every bucket is 0: there was no prompt to hit
        }
    ]
    client = TestClient(create_app(make_settings(rows=rows)))

    body = client.get("/api/overview").json()

    assert body["cache_hit_rate"] is None
    assert body["by_model"][0]["cache_hit_rate"] is None
    assert client.get("/api/overview").json()["total_tokens"] == 0


def test_rate_honors_window(client):
    windowed = client.get("/api/overview", params={"start": _DAY_A, "end": _DAY_A}).json()
    assert windowed["cache_hit_rate"] == 0.625

    empty = client.get("/api/overview", params={"start": "2026-01-01", "end": "2026-01-02"}).json()
    assert empty["cache_hit_rate"] is None


def test_rate_per_source_selection(make_settings):
    """Two channels on the same day keep their own rates under ?source=."""
    rows = [
        *_NESTED_ROWS,
        {
            "provider_id": "chan-other",
            "model_id": "model-b",
            "started_at": _ms(_DAY_A),
            "input_tokens": 1_000_000,
            "cache_read_input_tokens": 200_000,
            "computed_total_tokens": 1_000_000,
        },
    ]
    client = TestClient(create_app(make_settings(rows=rows)))

    only_b = client.get("/api/overview", params={"source": "zcode"}).json()
    rates = {m["model_id"]: m["cache_hit_rate"] for m in only_b["by_model"]}
    # merged total differs from each row: 2.2M read over 3.2M + 1M prompts
    assert only_b["cache_hit_rate"] == round(2_200_000 / 4_200_000, 6)
    assert rates == {"priced": 0.625, "model-b": 0.2}

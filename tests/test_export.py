"""T22: /api/export — fixed-shape Markdown per-model table.

Raw integers only (exported numbers get recomputed), null cost written as
未计价 never 0, header carries the methodology so the file survives alone.
"""

import json
from datetime import datetime

from fastapi.testclient import TestClient

from zlens.api.app import create_app


def _ms(day: str) -> int:
    dt = datetime.fromisoformat(f"{day}T12:00:00").astimezone()
    return int(dt.timestamp() * 1000)


_ROWS = [
    {
        "provider_id": "chan-a",
        "model_id": "model-a",
        "started_at": _ms("2026-08-01"),
        "input_tokens": 1_000_000,
        "computed_total_tokens": 1_000_000,
    },
    {
        "provider_id": "chan-b",
        "model_id": "model-b",
        "started_at": _ms("2026-08-15"),
        "input_tokens": 500_000,
        "computed_total_tokens": 500_000,
    },
]

_PRICES = {"zcode|chan-a|model-a": {"input": 1.0, "output": 0.0}}


def _client(make_settings, tmp_path, rows, prices=None):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps({"version": 1, "models": prices if prices is not None else _PRICES}),
        encoding="utf-8",
    )
    return TestClient(create_app(make_settings(rows=rows, pricing_path=pricing_path)))


def test_headers_and_filename(make_settings, tmp_path):
    client = _client(make_settings, tmp_path, _ROWS)

    response = client.get("/api/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    assert "zlens-models-20" in response.headers["content-disposition"]


def test_raw_integers_and_unpriced_marker(make_settings, tmp_path):
    client = _client(make_settings, tmp_path, _ROWS)

    text = client.get("/api/export").text

    assert "| 1000000 |" in text  # raw token integer, not 100.0 万
    assert "| 1 |" in text or "| 1  |" in text  # bare cost, no ¥ symbol
    assert "¥" not in text
    assert "未计价" in text  # chan-b has no price
    assert "| 0 |" not in text.split("\n\n")[-1] or "model-b | 1 | 500000" in text
    assert "model-b" in text


def test_header_carries_methodology_and_generation_time(make_settings, tmp_path):
    client = _client(make_settings, tmp_path, _ROWS)

    text = client.get("/api/export").text

    assert "四档互斥" in text
    assert "未计价" in text
    assert "生成时间" in text
    assert "别名" in text


def test_empty_data_renders_header_only(make_settings, tmp_path):
    client = _client(make_settings, tmp_path, [])

    text = client.get("/api/export").text

    assert "四档互斥" in text
    assert not any(line.startswith("| zcode") for line in text.splitlines())  # no data rows


def test_all_unpriced_marks_every_row(make_settings, tmp_path):
    client = _client(make_settings, tmp_path, _ROWS, prices={})

    text = client.get("/api/export").text

    data_rows = [line for line in text.splitlines() if line.startswith("| zcode")]
    assert len(data_rows) == 2
    assert all("未计价" in line for line in data_rows)


def test_window_source_and_sort_all_apply(make_settings, tmp_path):
    client = _client(make_settings, tmp_path, _ROWS)

    windowed = client.get("/api/export", params={"start": "2026-08-15", "end": "2026-08-15"}).text
    assert "model-a" not in windowed and "model-b" in windowed

    ordered = client.get("/api/export", params={"sort": "estimated_cost"}).text
    a_pos, b_pos = ordered.index("model-a"), ordered.index("model-b")
    assert a_pos < b_pos  # priced row first, unpriced sinks to the bottom

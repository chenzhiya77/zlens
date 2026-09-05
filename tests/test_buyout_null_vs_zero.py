"""T14: buyout_total must distinguish "never filled" (null) from "paid zero" (0.0).

AGENTS.md: 把「没填」显示成 ¥0.00 就是撒谎。四种组合见各用例。
"""

import json

from fastapi.testclient import TestClient

from zlens.api.app import create_app
from zlens.core.config import Settings

_KEY_A = "zcode|chan-a|plan-a"
_KEY_B = "zcode|chan-b|plan-b"

_ROWS = [
    {
        "provider_id": "chan-a",
        "model_id": "plan-a",
        "input_tokens": 1000,
        "computed_total_tokens": 1000,
    }
]


def _client(make_db, tmp_path, prices):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps({"version": 1, "models": prices}), encoding="utf-8")
    app = create_app(
        Settings(
            db_path=make_db(_ROWS),
            pricing_path=pricing_path,
            minimax_sessions_dir=tmp_path / "minimax-missing",
            opencode_db_path=tmp_path / "opencode-missing.db",
            workbuddy_dir=tmp_path / "workbuddy-missing",
            qoder_cn_config_dir=tmp_path / "qoder-cn-missing",
            qoder_config_dir=tmp_path / "qoder-missing",
            claude_config_dir=tmp_path / "claude-missing",
        )
    )
    return TestClient(app)


def test_no_buyout_rows_means_null_not_zero(make_db, tmp_path):
    """价格表里一条买断行都没有 → null,不是 0:界面要显示「未填」。"""
    client = _client(make_db, tmp_path, {_KEY_A: {"input": 3.0, "output": 15.0}})

    assert client.get("/api/overview").json()["buyout_total"] is None


def test_filled_zero_is_zero_and_not_null(make_db, tmp_path):
    """真填了 0(免费套餐)→ 0.0,不能与「没填」混同。"""
    client = _client(
        make_db, tmp_path, {_KEY_A: {"input": 3.0, "output": 15.0, "buyout_amount": 0}}
    )

    body = client.get("/api/overview").json()
    assert body["buyout_total"] == 0.0
    # 两笔钱照旧分开:买断 0 不吞掉也不替代按量估算(0.003 = 1000 × ¥3/M)
    assert body["estimated_cost"] == 0.003


def test_unfilled_row_alongside_zero_row_still_sums_to_zero(make_db, tmp_path):
    """一行没填 + 一行填 0 → 0.0:空值不参与求和,也不把总数拖回 null。"""
    client = _client(
        make_db,
        tmp_path,
        {
            _KEY_A: {"input": 3.0, "output": 15.0},
            _KEY_B: {"input": 1.0, "output": 2.0, "buyout_amount": 0},
        },
    )

    assert client.get("/api/overview").json()["buyout_total"] == 0.0


def test_multi_row_sum_skips_unfilled_rows(make_db, tmp_path):
    """多行买断正确求和;没填的行不按 0 处理、也不改变求和结果。"""
    client = _client(
        make_db,
        tmp_path,
        {
            _KEY_A: {"input": 3.0, "output": 15.0, "buyout_amount": 299.0},
            _KEY_B: {"input": 1.0, "output": 2.0},
        },
    )

    assert client.get("/api/overview").json()["buyout_total"] == 299.0

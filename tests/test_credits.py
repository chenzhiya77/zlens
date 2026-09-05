"""T31 契约语义:三笔账互不相加、null-vs-0、占位 token 不乘价、credit_prices 派生量。

积分来源适配器尚未落地(T32/T33),这里按 T31 的方式直接构造契约对象,
锁定成本层的行为;HTTP 侧的口径由 T32/T33 的 fixture 复验。
"""

import json

import pytest

from zlens.core.cost import PriceTable, enrich_overview, fold_daily
from zlens.sources.models import DailyModelUsage, ModelUsageSummary, Overview


def _credit_row(**overrides) -> ModelUsageSummary:
    fields = dict(
        source="workbuddy",
        provider_id="auto",
        model_id="glm-5.2",
        request_count=3,
        input_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        total_tokens=0,
        credits=100.0,
        original_credits=150.0,
        tokens_reported=False,
        credits_reported=True,
    )
    fields.update(overrides)
    return ModelUsageSummary(**fields)


def _token_row(**overrides) -> ModelUsageSummary:
    fields = dict(
        source="zcode",
        provider_id="chan",
        model_id="m1",
        request_count=1,
        input_tokens=1_000_000,
        output_tokens=0,
        reasoning_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        total_tokens=1_000_000,
    )
    fields.update(overrides)
    return ModelUsageSummary(**fields)


def _table(tmp_path, payload) -> PriceTable:
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return PriceTable.load(path)


def test_v1_price_table_loads_unchanged(tmp_path):
    table = _table(
        tmp_path,
        {"version": 1, "models": {"zcode|chan|m1": {"input": 3.0, "output": 15.0}}},
    )
    assert table.version == 1
    assert table.models["zcode|chan|m1"].input == 3.0
    assert table.credit_prices == {}


def test_credit_prices_drops_invalid_entries_keeps_valid(tmp_path):
    table = _table(
        tmp_path,
        {
            "version": 2,
            "credit_prices": {
                "workbuddy|plan": {"cny_per_credit": 0.0495},
                "workbuddy|bogus": {"cny_per_credit": 0.05},  # 非法 basis
                "workbuddy": {"cny_per_credit": 0.05},  # 缺 basis
                "trae_cn|pack": {"cny_per_credit": -1},  # 非正数
                "qoder_cn|plan": {"cny_per_credit": "0.05"},  # 非数值
                "qoder_cn|pack": {"cny_per_credit": 0.04, "note": "¥40/1000"},
            },
        },
    )
    assert table.credit_price_for("workbuddy", "plan").cny_per_credit == 0.0495
    assert table.credit_price_for("qoder_cn", "pack").cny_per_credit == 0.04
    assert table.credit_price_for("workbuddy", "pack") is None
    assert table.credit_price_for("qoder_cn", "plan") is None
    assert "workbuddy|bogus" not in table.credit_prices


def test_placeholder_tokens_are_never_priced(tmp_path):
    # Token price exists for the credit channel — it must still not be applied:
    # the zeros are placeholders, the money lives in the credit ledger.
    table = _table(
        tmp_path,
        {
            "models": {"workbuddy|auto|glm-5.2": {"input": 3.0, "output": 15.0}},
            "credit_prices": {
                "workbuddy|plan": {"cny_per_credit": 0.0495},
                "workbuddy|pack": {"cny_per_credit": 0.05},
            },
        },
    )
    overview = enrich_overview(
        Overview(
            request_count=1,
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_tokens=0,
            by_model=[_credit_row()],
        ),
        table,
    )
    row = overview.by_model[0]
    assert row.estimated_cost is None
    assert row.tokens_reported is False
    assert overview.credit_total == 100.0
    assert overview.credit_original_total == 150.0
    assert overview.discount_credits == 50.0
    assert overview.credit_value_cny.plan == pytest.approx(4.95, abs=1e-9)
    assert overview.credit_value_cny.pack == 5.0
    # The third ledger never leaks into estimated_cost:
    assert overview.estimated_cost == 0.0


def test_credit_value_bases_degrade_independently(tmp_path):
    table = _table(
        tmp_path,
        {"credit_prices": {"workbuddy|plan": {"cny_per_credit": 0.0495}}},
    )
    overview = enrich_overview(
        Overview(
            request_count=1,
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_tokens=0,
            by_model=[_credit_row()],
        ),
        table,
    )
    # 只填 plan 不填 pack:plan 照常计算,pack 单独为 null(spec 验收 3)。
    assert overview.credit_value_cny.plan == pytest.approx(4.95, abs=1e-9)
    assert overview.credit_value_cny.pack is None


def test_credit_value_null_when_any_reporting_source_unpriced(tmp_path):
    table = _table(
        tmp_path,
        {"credit_prices": {"workbuddy|plan": {"cny_per_credit": 0.0495}}},
    )
    overview = enrich_overview(
        Overview(
            request_count=2,
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_tokens=0,
            by_model=[
                _credit_row(),
                _credit_row(source="qoder_cn", provider_id="qoder", model_id="qfmodel"),
            ],
        ),
        table,
    )
    assert overview.credit_total == 200.0
    # qoder_cn 没录 plan 价 → 该 basis 整体 null(半张账单会系统性低估)。
    assert overview.credit_value_cny.plan is None
    assert overview.credit_value_cny.pack is None


def test_discount_needs_both_sides():
    overview = enrich_overview(
        Overview(
            request_count=1,
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_tokens=0,
            by_model=[_credit_row(original_credits=None)],
        ),
        PriceTable(),
    )
    assert overview.credit_total == 100.0
    assert overview.credit_original_total is None
    assert overview.discount_credits is None


def test_overview_without_credit_rows_has_no_credit_ledger():
    overview = enrich_overview(
        Overview(
            request_count=1,
            input_tokens=1_000_000,
            output_tokens=0,
            reasoning_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_tokens=1_000_000,
            by_model=[_token_row()],
        ),
        PriceTable(),
    )
    assert overview.credit_total is None
    assert overview.credit_value_cny is None
    assert overview.discount_credits is None
    assert overview.tokens_reported is True
    assert overview.credits_reported is False


def test_fold_daily_mixed_sources_flags_and_sums():
    table = PriceTable()
    rows = [
        DailyModelUsage(
            source="zcode",
            day="2026-09-01",
            provider_id="chan",
            model_id="m1",
            request_count=1,
            input_tokens=1000,
            output_tokens=0,
            reasoning_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_tokens=1000,
        ),
        DailyModelUsage(
            source="workbuddy",
            day="2026-09-01",
            provider_id="auto",
            model_id="glm-5.2",
            request_count=2,
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_tokens=0,
            credits=12.5,
            tokens_reported=False,
            credits_reported=True,
        ),
    ]
    trends = fold_daily(rows, table)
    day = trends.days[0]
    assert day.credits == 12.5
    assert day.original_credits is None
    assert day.tokens_reported is False
    assert day.credits_reported is True
    assert day.total_tokens == 1000
    # by_model 行原样带口径标记
    flags = {r.source: (r.tokens_reported, r.credits_reported) for r in trends.by_model}
    assert flags == {"zcode": (True, False), "workbuddy": (False, True)}

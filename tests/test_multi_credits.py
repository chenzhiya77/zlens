"""T31 合并语义:积分忽略 null 求和、口径标记、上报来源集合、meta 并集。

积分来源适配器尚未落地(T32/T33),用协议形状的假适配器锁定 MultiSource 的
合并契约;真实 fixture 的复验随各自适配器票走。
"""

from datetime import datetime

from zlens.sources.models import (
    HealthReport,
    MetaInfo,
    ModelsRanking,
    ModelUsageSummary,
    Overview,
)
from zlens.sources.multi import MultiSource


def _row(
    source,
    model_id,
    *,
    tokens=0,
    credits=None,
    original=None,
    tokens_reported=True,
    credits_reported=False,
) -> ModelUsageSummary:
    return ModelUsageSummary(
        source=source,
        provider_id="prov",
        model_id=model_id,
        request_count=1,
        input_tokens=tokens,
        output_tokens=0,
        reasoning_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        total_tokens=tokens,
        credits=credits,
        original_credits=original,
        tokens_reported=tokens_reported,
        credits_reported=credits_reported,
    )


class FakeSource:
    """SourceAdapter-shaped fake; traits are declared on MetaInfo like the real
    adapters do (token sources list themselves, credit sources do not)."""

    def __init__(
        self, source_id: str, rows: list[ModelUsageSummary], reports_credits: bool = False
    ) -> None:
        self.id = source_id
        self._rows = rows
        self._reports_credits = reports_credits

    def is_available(self) -> bool:
        return True

    def model_ids(self) -> list[str]:
        return sorted({row.model_id for row in self._rows})

    def model_keys(self, window=None) -> list[str]:
        return sorted({f"{self.id}|prov|{row.model_id}" for row in self._rows})

    def meta(self, window=None) -> MetaInfo:
        return MetaInfo(
            source_id=self.id,
            request_count=len(self._rows),
            first_request_at=None,
            last_request_at=None,
            generated_at=datetime.now().astimezone(),
            credit_reporting_sources=[self.id] if self._reports_credits else [],
            token_reporting_sources=[] if self._reports_credits else [self.id],
        )

    def overview(self, window=None) -> Overview:
        rows = list(self._rows)
        return Overview(
            request_count=len(rows),
            input_tokens=sum(row.input_tokens for row in rows),
            output_tokens=sum(row.output_tokens for row in rows),
            reasoning_tokens=sum(row.reasoning_tokens for row in rows),
            cache_creation_tokens=sum(row.cache_creation_tokens for row in rows),
            cache_read_tokens=sum(row.cache_read_tokens for row in rows),
            total_tokens=sum(row.total_tokens for row in rows),
            by_model=rows,
        )

    def daily_by_model(self, window=None) -> list:
        return []

    def models_ranking(self, window=None) -> ModelsRanking:
        return ModelsRanking(models=list(self._rows))

    def usage_by_project_model(self) -> list:
        return []

    def latency_samples(self, window=None) -> tuple[list[int], list[int]]:
        return ([], [])

    def health_summary(self, window=None) -> HealthReport:
        return HealthReport(
            request_count=len(self._rows),
            requests_with_retries=0,
            total_retries=0,
            cancelled_by_user=0,
            context_exceeded=0,
            errored_requests=0,
            errors=[],
        )


def _merged() -> MultiSource:
    return MultiSource(
        [
            FakeSource(
                "zcode",
                [_row("zcode", "m1", tokens=1000)],
            ),
            FakeSource(
                "workbuddy",
                [
                    _row(
                        "workbuddy",
                        "glm-5.2",
                        credits=12.5,
                        original=20.0,
                        tokens_reported=False,
                        credits_reported=True,
                    )
                ],
                reports_credits=True,
            ),
        ]
    )


def test_credits_merge_ignores_null_sum():
    body = _merged().overview()
    # 积分合计只来自上报来源;token 合计不掺积分来源的占位 0 以外的任何影响。
    assert body.credits == 12.5
    assert body.original_credits == 20.0
    assert body.total_tokens == 1000
    # 混入不报 token 的来源后,合并口径必须显式标 Partial。
    assert body.tokens_reported is False
    assert body.credits_reported is True
    assert body.credit_reporting_sources == ["workbuddy"]
    assert body.token_reporting_sources == ["zcode"]
    flags = {row.source: (row.tokens_reported, row.credits_reported) for row in body.by_model}
    assert flags == {"zcode": (True, False), "workbuddy": (False, True)}


def test_token_only_merge_has_no_credit_ledger():
    store = MultiSource(
        [
            FakeSource("zcode", [_row("zcode", "m1", tokens=1000)]),
            FakeSource("minimax", [_row("minimax", "M3", tokens=500)]),
        ]
    )
    body = store.overview()
    assert body.credits is None
    assert body.original_credits is None
    assert body.credit_value_cny is None
    assert body.tokens_reported is True
    assert body.credits_reported is False
    assert body.credit_reporting_sources == []
    assert sorted(body.token_reporting_sources) == ["minimax", "zcode"]


def test_meta_unions_reporting_lists_and_selection_scopes_them():
    store = _merged()
    meta = store.meta()
    assert meta.credit_reporting_sources == ["workbuddy"]
    assert meta.token_reporting_sources == ["zcode"]

    only_credit = store.select("workbuddy").meta()
    assert only_credit.credit_reporting_sources == ["workbuddy"]
    assert only_credit.token_reporting_sources == []

    only_token = store.select("zcode").meta()
    assert only_token.credit_reporting_sources == []
    assert only_token.token_reporting_sources == ["zcode"]


def test_empty_rows_merge_is_vacuously_token_reported():
    store = MultiSource([FakeSource("zcode", [])])
    body = store.overview()
    assert body.credits is None
    assert body.tokens_reported is True
    assert body.credit_reporting_sources == []

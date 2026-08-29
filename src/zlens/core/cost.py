"""Cost estimation over an editable price table (see pricing.example.json).

Prices are per 1M tokens in CNY — the app's single money base. Dollar prices are
folded into CNY while they are entered (the pricing form converts a recognised $
screenshot using the user's own `fx_usd_cny`), never while costing, so no stored
number depends on a rate that could change later. The table is keyed per channel —
`source|provider_id|model_id` (see model_key) — because the same model served
through different channels can be priced differently; nothing is ever merged across
channels. A channel absent from the table is never priced: it renders tokens-only
with a null cost, and the overview total stays null while any served model is
unpriced (a partial total would silently understate spend). A row may additionally
carry `buyout_amount`, the one-off CNY paid for a plan: it is summed into its own
overview total, never amortised into a per-token price and never added to the
consumption figure — paid money and burned money answer different questions. A
malformed price file degrades to an empty table rather than failing requests: a
pricing typo must never break the app.
"""

import json
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from zlens.sources.models import (
    DailyModelUsage,
    DailyTrends,
    DailyUsage,
    MetricDelta,
    Overview,
    OverviewTotals,
    ProjectModelUsage,
    ProjectsReport,
    ProjectUsage,
    model_key,
)

_TOKENS_PER_PRICE_UNIT = 1_000_000

_SUMMARY_KEYS = (
    "request_count",
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
    "total_tokens",
)


class ModelPrice(BaseModel):
    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0
    # One-off CNY paid for a buyout/plan channel. Nullable on purpose: an unfilled
    # row must stay distinguishable from a deliberate 0. Never used per request —
    # buyout money is already spent, so it is only ever summed as its own total.
    buyout_amount: float | None = None


class PriceTable(BaseModel):
    version: int = 1
    # Keyed by channel (see model_key), never by bare model_id. All prices CNY.
    models: dict[str, ModelPrice] = {}
    # Rate the pricing form folds $ prices with at entry time. Never used in
    # costing, and deliberately without a default: inventing a market rate would
    # fabricate spend.
    fx_usd_cny: float | None = None

    @classmethod
    def load(cls, path: Path) -> "PriceTable":
        if not path.exists():
            return cls()
        try:
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return cls()

    def price_for(self, key: str) -> ModelPrice | None:
        return self.models.get(key)

    def buyout_total(self) -> float | None:
        """Money already paid for buyout/plan rows, independent of any usage.

        None means the table has no buyout row at all: "never filled" and "paid
        exactly zero" are different facts and must render differently. Filled rows
        make the total a number even when that number is 0; unfilled (null) rows
        are skipped rather than read as zero.
        """
        amounts = [
            price.buyout_amount for price in self.models.values() if price.buyout_amount is not None
        ]
        if not amounts:
            return None
        return round(sum(amounts), 6)

    def estimate_cost(
        self,
        key: str,
        *,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int,
        cache_read_tokens: int,
    ) -> float | None:
        # Safe to price each tier separately only because adapters hand over disjoint
        # buckets (see the contract in sources/models.py): a source that nests the
        # cached prefix inside its input would make this charge those tokens twice.
        price = self.price_for(key)
        if price is None:
            return None
        return (
            input_tokens * price.input
            + output_tokens * price.output
            + cache_read_tokens * price.cache_read
            + cache_creation_tokens * price.cache_write
        ) / _TOKENS_PER_PRICE_UNIT


def _cost_of(item, table: PriceTable) -> float | None:
    return table.estimate_cost(
        model_key(item.source, item.provider_id, item.model_id),
        input_tokens=item.input_tokens,
        output_tokens=item.output_tokens,
        cache_creation_tokens=item.cache_creation_tokens,
        cache_read_tokens=item.cache_read_tokens,
    )


def attach_model_costs(models, table: PriceTable):
    return [m.model_copy(update={"estimated_cost": _cost_of(m, table)}) for m in models]


def _cache_hit_rate(cache_read: int, cache_creation: int, billed_input: int) -> float | None:
    """cache_read over all prompt tokens (方案 A: 分母含缓存写).

    The buckets are mutually exclusive by contract, so input + cache_read +
    cache_creation is the whole prompt. Denominator 0 means there was no prompt
    at all — that is "unknown" (None), never a fabricated 0% or 100%.
    """
    denominator = billed_input + cache_read + cache_creation
    if denominator == 0:
        return None
    return round(cache_read / denominator, 6)


def enrich_overview(overview: Overview, table: PriceTable) -> Overview:
    """Attach per-model costs; the total only appears when every model is priced.

    The buyout total rides along ungated: it is money already paid for a plan, so a
    missing per-token price cannot make it unknown. The two figures answer different
    questions and are never added together.
    """
    by_model = attach_model_costs(overview.by_model, table)
    by_model = [
        m.model_copy(
            update={
                "cache_hit_rate": _cache_hit_rate(
                    m.cache_read_tokens, m.cache_creation_tokens, m.input_tokens
                )
            }
        )
        for m in by_model
    ]
    fully_priced = bool(by_model) and all(m.estimated_cost is not None for m in by_model)
    total = round(sum(m.estimated_cost for m in by_model), 6) if fully_priced else None
    totals = OverviewTotals(
        request_count=overview.request_count,
        input_tokens=overview.input_tokens,
        output_tokens=overview.output_tokens,
        reasoning_tokens=overview.reasoning_tokens,
        cache_creation_tokens=overview.cache_creation_tokens,
        cache_read_tokens=overview.cache_read_tokens,
        total_tokens=overview.total_tokens,
        estimated_cost=total,
    )
    return overview.model_copy(
        update={
            "by_model": by_model,
            "estimated_cost": total,
            "buyout_total": table.buyout_total(),
            "cache_hit_rate": _cache_hit_rate(
                overview.cache_read_tokens, overview.cache_creation_tokens, overview.input_tokens
            ),
            "totals": totals,
        },
    )


def fold_projects(rows: list[ProjectModelUsage], table: PriceTable) -> ProjectsReport:
    """Fold per-model-per-project rows into project totals.

    Same honesty rule as the daily fold: a project's cost stays null while any
    model contributing to it is unpriced.
    """
    priced_rows = attach_model_costs(rows, table)
    totals: dict[str, dict[str, int]] = {}
    titles: dict[str, str] = {}
    project_sources: dict[str, set[str]] = {}
    project_costs: dict[str, float] = {}
    unpriced_projects: set[str] = set()
    for row in priced_rows:
        acc = totals.setdefault(row.directory, dict.fromkeys(_SUMMARY_KEYS, 0))
        titles.setdefault(row.directory, row.title)
        project_sources.setdefault(row.directory, set()).add(row.source)
        for key in _SUMMARY_KEYS:
            acc[key] += getattr(row, key)
        if row.estimated_cost is None:
            unpriced_projects.add(row.directory)
        else:
            project_costs[row.directory] = (
                project_costs.get(row.directory, 0.0) + row.estimated_cost
            )

    projects = [
        ProjectUsage(
            directory=directory,
            title=titles[directory],
            source="+".join(sorted(project_sources[directory])),
            estimated_cost=(
                None if directory in unpriced_projects else round(project_costs[directory], 6)
            ),
            **totals[directory],
        )
        for directory in sorted(totals, key=lambda d: totals[d]["total_tokens"], reverse=True)
    ]
    return ProjectsReport(projects=projects)


def _fold_usage(
    rows: list[DailyModelUsage], table: PriceTable, bucket: Callable[[DailyModelUsage], str]
) -> tuple[list[DailyUsage], list[DailyModelUsage]]:
    """The one fold both granularities share (T17): token buckets always sum
    (they don't depend on the price table), while a bucket's cost stays null
    when any model serving it is unpriced — same honesty rule as the overview.
    """
    by_model = attach_model_costs(rows, table)
    totals: dict[str, dict[str, int]] = {}
    costs: dict[str, float] = {}
    sources: dict[str, set[str]] = {}
    unpriced: set[str] = set()
    for row in by_model:
        key = bucket(row)
        acc = totals.setdefault(key, dict.fromkeys(_SUMMARY_KEYS, 0))
        sources.setdefault(key, set()).add(row.source)
        for key_field in _SUMMARY_KEYS:
            acc[key_field] += getattr(row, key_field)
        if row.estimated_cost is None:
            unpriced.add(key)
        else:
            costs[key] = costs.get(key, 0.0) + row.estimated_cost

    usage = [
        DailyUsage(
            day=key,
            source="+".join(sorted(sources[key])),
            estimated_cost=None if key in unpriced else round(costs[key], 6),
            **totals[key],
        )
        for key in sorted(totals)
    ]
    return usage, by_model


def fold_daily(rows: list[DailyModelUsage], table: PriceTable) -> DailyTrends:
    """Fold per-model-per-day rows into daily totals plus the long-format series.

    A day's total cost stays null when any model serving that day is unpriced,
    mirroring the overview rule: partial totals would understate spend.
    """
    usage, by_model = _fold_usage(rows, table, lambda row: row.day)
    return DailyTrends(days=usage, by_model=by_model, granularity="day")


def fold_monthly(rows: list[DailyModelUsage], table: PriceTable) -> DailyTrends:
    """Same fold with the bucket cut to 'YYYY-MM' — the「全部」view.

    Reuses _fold_usage, so one unpriced day poisons its whole month's cost the
    same way it poisons a day. Months without data never appear: no zero-filled
    fake months just to draw a fuller x axis.
    """
    usage, by_model = _fold_usage(rows, table, lambda row: row.day[:7])
    return DailyTrends(days=usage, by_model=by_model, granularity="month")


def metric_delta(current: float | int | None, previous: float | int | None) -> MetricDelta:
    """环比 of one metric (T16). previous rides along whenever it was measured;
    change_rate needs both sides and a non-zero base — null means "cannot say",
    never "no change", and a 0 base must not produce Infinity."""
    change = None
    if current is not None and previous is not None and previous != 0:
        change = round((current - previous) / previous, 6)
    return MetricDelta(previous=previous, change_rate=change)

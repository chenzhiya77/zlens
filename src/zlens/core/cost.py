"""Cost estimation over an editable price table (see pricing.example.json).

Prices are per 1M tokens in CNY — the app's single money base. Dollar prices are
folded into CNY while they are entered (the pricing form converts a recognised $
screenshot using the user's own `fx_usd_cny`), never while costing, so no stored
number depends on a rate that could change later. The table is keyed per channel —
`source|provider_id|model_id` (see model_key) — because the same model served
through different channels can be priced differently; nothing is ever merged across
channels. A channel absent from the table is never priced: its row renders
tokens-only with a null cost, and aggregates count it as ¥0 — an unfilled price
reads as free (product decision 2026-09-02), so the money figure always ships;
which channels lack prices stays visible on the rows themselves and in the
pricing page's 待补价 group. A row may additionally
carry `buyout_amount`, the one-off CNY paid for a plan: it is summed into its own
overview total, never amortised into a per-token price and never added to the
consumption figure — paid money and burned money answer different questions. A
malformed price file degrades to an empty table rather than failing requests: a
pricing typo must never break the app.
"""

import json
import math
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, field_validator

from zlens.sources.models import (
    CreditBySource,
    CreditValueCny,
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

# Basis keys of `credit_prices` (`source|basis`). Both rates are real prices
# answering different questions (subscription-equivalent vs add-on-pack), so
# they coexist and are rendered side by side — never auto-picked-low.
_CREDIT_BASES = frozenset({"plan", "pack"})

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


class CreditPrice(BaseModel):
    """List price of one credit for a source (¥/积分), keyed `source|basis`.

    It prices the third ledger (`credits`) into `credit_value_cny` — a
    list-price conversion, never actual spend, and never a token price.
    """

    cny_per_credit: float
    note: str | None = None


class PriceTable(BaseModel):
    # Version is informational: v2 files carry `credit_prices`, v1 files parse
    # identically without it (the field default keeps an empty table at v1 —
    # the shape is additive, nothing reads the number to branch).
    version: int = 1
    # Keyed by channel (see model_key), never by bare model_id. All prices CNY.
    models: dict[str, ModelPrice] = {}
    # Credit list prices keyed `source|basis`; invalid entries are dropped at
    # parse time (a pricing typo must never break the app — same degrade
    # discipline as the file-level fallback below).
    credit_prices: dict[str, CreditPrice] = {}
    # Rate the pricing form folds $ prices with at entry time. Never used in
    # costing, and deliberately without a default: inventing a market rate would
    # fabricate spend.
    fx_usd_cny: float | None = None

    @field_validator("credit_prices", mode="before")
    @classmethod
    def _drop_invalid_credit_prices(cls, value: object) -> dict[str, object]:
        """Drop invalid entries instead of failing the whole table.

        A `credit_prices` entry must be `"<source>|<basis>": {cny_per_credit > 0}`
        with basis ∈ {plan, pack}; anything else (wrong basis, non-positive or
        non-numeric rate, non-dict payload) is discarded here so a typo costs
        that entry, never the app.
        """
        if not isinstance(value, dict):
            return {}
        kept: dict[str, dict[str, object]] = {}
        for key, entry in value.items():
            if not isinstance(key, str) or not isinstance(entry, dict):
                continue
            source, _, basis = key.rpartition("|")
            if not source or basis not in _CREDIT_BASES:
                continue
            rate = entry.get("cny_per_credit")
            if (
                isinstance(rate, bool)
                or not isinstance(rate, (int, float))
                or not math.isfinite(rate)
                or rate <= 0
            ):
                continue
            note = entry.get("note")
            kept[key] = {
                "cny_per_credit": float(rate),
                "note": note if isinstance(note, str) and note.strip() else None,
            }
        return kept

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

    def credit_price_for(self, source: str, basis: str) -> CreditPrice | None:
        """¥/credit for one source under one basis; None = not filled."""
        return self.credit_prices.get(f"{source}|{basis}")

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
    if not item.tokens_reported:
        # Placeholder zeros must never be priced: a credits-billed source has no
        # token tiers, its money lives in credit_value_cny (the third ledger).
        return None
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


def _credit_value_cny(credit_rows, table: PriceTable) -> CreditValueCny | None:
    """List-price conversion of consumed credits, per basis (the third ledger).

    A credit-reporting source missing the basis price nulls exactly that basis —
    pricing only some sources would systematically understate the bill. The
    result is a list-price figure (标价值), never actual spend, and never a
    token-side amount.
    """
    if not credit_rows:
        return None
    sources = {row.source for row in credit_rows}
    values: dict[str, float | None] = {}
    for basis in sorted(_CREDIT_BASES):
        prices = [table.credit_price_for(source, basis) for source in sources]
        if any(price is None for price in prices):
            values[basis] = None
            continue
        values[basis] = round(
            sum(
                row.credits * table.credit_price_for(row.source, basis).cny_per_credit
                for row in credit_rows
            ),
            6,
        )
    return CreditValueCny(**values)


def enrich_overview(overview: Overview, table: PriceTable) -> Overview:
    """Attach per-model costs; the total always ships — unpriced rows count as ¥0
    (an unfilled price reads as free), and rows keep their null cost as the
    "not priced yet" marker.

    The buyout total rides along ungated: it is money already paid for a plan, so a
    missing per-token price cannot make it unknown. The two figures answer different
    questions and are never added together — and the third ledger
    (`credit_total`/`credit_value_cny`) rides along the same way: credits are
    priced from `credit_prices`, never folded into `estimated_cost`, and none of
    the three totals is ever added to another.
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
    total = round(sum(m.estimated_cost or 0 for m in by_model), 6)
    credit_rows = [m for m in by_model if m.credits is not None]
    # Credit counts are a per-source unit: WorkBuddy's 1 credit and Qoder CN's 1
    # credit convert to different CNY, so a flat sum across sources is a fake
    # ledger. The flat totals exist only while exactly one source reports
    # credits; with two or more they go null and the per-source ledgers in
    # credit_by_source take over. Money stays cross-source comparable —
    # credit_value_cny prices each row at its own source's rate.
    credit_sources = sorted({m.source for m in credit_rows})
    single_source_rows = credit_rows if len(credit_sources) == 1 else []
    credit_total = (
        round(sum(m.credits for m in single_source_rows), 6) if single_source_rows else None
    )
    original_rows = [m for m in single_source_rows if m.original_credits is not None]
    credit_original_total = (
        round(sum(m.original_credits for m in original_rows), 6) if original_rows else None
    )
    discount_credits = (
        round(credit_original_total - credit_total, 6)
        if credit_total is not None and credit_original_total is not None
        else None
    )

    def _source_ledger(source: str) -> CreditBySource:
        rows = [m for m in credit_rows if m.source == source]
        original = [m.original_credits for m in rows if m.original_credits is not None]
        credits_sum = round(sum(m.credits for m in rows), 6)
        original_sum = round(sum(original), 6) if original else None
        return CreditBySource(
            source=source,
            credits=credits_sum,
            original_credits=original_sum,
            discount_credits=(
                round(original_sum - credits_sum, 6) if original_sum is not None else None
            ),
        )

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
            "credit_total": credit_total,
            "credit_original_total": credit_original_total,
            "discount_credits": discount_credits,
            "credit_value_cny": _credit_value_cny(credit_rows, table),
            "credit_by_source": [_source_ledger(source) for source in credit_sources],
        },
    )


def fold_projects(rows: list[ProjectModelUsage], table: PriceTable) -> ProjectsReport:
    """Fold per-model-per-project rows into project totals.

    Same rule as the daily fold: a project's cost always ships — unpriced rows
    count as ¥0 (an unfilled price reads as free).
    """
    priced_rows = attach_model_costs(rows, table)
    totals: dict[str, dict[str, int]] = {}
    titles: dict[str, str] = {}
    project_sources: dict[str, set[str]] = {}
    project_costs: dict[str, float] = {}
    project_credits: dict[str, float] = {}
    project_original: dict[str, float] = {}
    project_tokens_ok: dict[str, bool] = {}
    project_credits_rep: dict[str, bool] = {}
    for row in priced_rows:
        acc = totals.setdefault(row.directory, dict.fromkeys(_SUMMARY_KEYS, 0))
        titles.setdefault(row.directory, row.title)
        project_sources.setdefault(row.directory, set()).add(row.source)
        for key in _SUMMARY_KEYS:
            acc[key] += getattr(row, key)
        project_costs[row.directory] = project_costs.get(row.directory, 0.0) + (
            row.estimated_cost or 0
        )
        if row.credits is not None:
            project_credits[row.directory] = project_credits.get(row.directory, 0.0) + row.credits
        if row.original_credits is not None:
            project_original[row.directory] = project_original.get(row.directory, 0.0) + (
                row.original_credits
            )
        project_tokens_ok[row.directory] = (
            project_tokens_ok.get(row.directory, True) and row.tokens_reported
        )
        project_credits_rep[row.directory] = (
            project_credits_rep.get(row.directory, False) or row.credits_reported
        )

    projects = [
        ProjectUsage(
            directory=directory,
            title=titles[directory],
            source="+".join(sorted(project_sources[directory])),
            estimated_cost=round(project_costs[directory], 6),
            credits=(
                round(project_credits[directory], 6) if directory in project_credits else None
            ),
            original_credits=(
                round(project_original[directory], 6) if directory in project_original else None
            ),
            tokens_reported=project_tokens_ok.get(directory, True),
            credits_reported=project_credits_rep.get(directory, False),
            **totals[directory],
        )
        for directory in sorted(totals, key=lambda d: totals[d]["total_tokens"], reverse=True)
    ]
    return ProjectsReport(projects=projects)


def _fold_usage(
    rows: list[DailyModelUsage], table: PriceTable, bucket: Callable[[DailyModelUsage], str]
) -> tuple[list[DailyUsage], list[DailyModelUsage]]:
    """The one fold both granularities share (T17): token buckets always sum
    (they don't depend on the price table), and a bucket's cost always ships —
    unpriced rows count as ¥0 (an unfilled price reads as free).
    """
    by_model = attach_model_costs(rows, table)
    totals: dict[str, dict[str, int]] = {}
    costs: dict[str, float] = {}
    sources: dict[str, set[str]] = {}
    credits_by: dict[str, float] = {}
    original_by: dict[str, float] = {}
    tokens_ok: dict[str, bool] = {}
    credits_reported: dict[str, bool] = {}
    for row in by_model:
        key = bucket(row)
        acc = totals.setdefault(key, dict.fromkeys(_SUMMARY_KEYS, 0))
        sources.setdefault(key, set()).add(row.source)
        for key_field in _SUMMARY_KEYS:
            acc[key_field] += getattr(row, key_field)
        costs[key] = costs.get(key, 0.0) + (row.estimated_cost or 0)
        # Credits fold by ignore-null sum (a source without a credit ledger is
        # not missing data); the flags fold by all/any so a bucket mixing in a
        # non-token-reporting row is labeled partial.
        if row.credits is not None:
            credits_by[key] = credits_by.get(key, 0.0) + row.credits
        if row.original_credits is not None:
            original_by[key] = original_by.get(key, 0.0) + row.original_credits
        tokens_ok[key] = tokens_ok.get(key, True) and row.tokens_reported
        credits_reported[key] = credits_reported.get(key, False) or row.credits_reported

    usage = [
        DailyUsage(
            day=key,
            source="+".join(sorted(sources[key])),
            estimated_cost=round(costs[key], 6),
            credits=round(credits_by[key], 6) if key in credits_by else None,
            original_credits=round(original_by[key], 6) if key in original_by else None,
            tokens_reported=tokens_ok.get(key, True),
            credits_reported=credits_reported.get(key, False),
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

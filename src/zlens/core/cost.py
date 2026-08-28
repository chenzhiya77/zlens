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
from pathlib import Path

from pydantic import BaseModel

from zlens.sources.models import (
    DailyModelUsage,
    DailyTrends,
    DailyUsage,
    Overview,
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

    def buyout_total(self) -> float:
        """Money already paid for buyout/plan rows, independent of any usage.

        Nulls are skipped rather than read as zero: a row the user never filled
        must not look like a deliberate free purchase.
        """
        return round(
            sum(
                price.buyout_amount
                for price in self.models.values()
                if price.buyout_amount is not None
            ),
            6,
        )

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


def enrich_overview(overview: Overview, table: PriceTable) -> Overview:
    """Attach per-model costs; the total only appears when every model is priced.

    The buyout total rides along ungated: it is money already paid for a plan, so a
    missing per-token price cannot make it unknown. The two figures answer different
    questions and are never added together.
    """
    by_model = attach_model_costs(overview.by_model, table)
    fully_priced = bool(by_model) and all(m.estimated_cost is not None for m in by_model)
    total = round(sum(m.estimated_cost for m in by_model), 6) if fully_priced else None
    return overview.model_copy(
        update={
            "by_model": by_model,
            "estimated_cost": total,
            "buyout_total": table.buyout_total(),
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


def fold_daily(rows: list[DailyModelUsage], table: PriceTable) -> DailyTrends:
    """Fold per-model-per-day rows into daily totals plus the long-format series.

    A day's total cost stays null when any model serving that day is unpriced,
    mirroring the overview rule: partial totals would understate spend.
    """
    by_model = attach_model_costs(rows, table)
    totals: dict[str, dict[str, int]] = {}
    day_costs: dict[str, float] = {}
    day_sources: dict[str, set[str]] = {}
    unpriced_days: set[str] = set()
    for row in by_model:
        acc = totals.setdefault(row.day, dict.fromkeys(_SUMMARY_KEYS, 0))
        day_sources.setdefault(row.day, set()).add(row.source)
        for key in _SUMMARY_KEYS:
            acc[key] += getattr(row, key)
        if row.estimated_cost is None:
            unpriced_days.add(row.day)
        else:
            day_costs[row.day] = day_costs.get(row.day, 0.0) + row.estimated_cost

    days = [
        DailyUsage(
            day=day,
            source="+".join(sorted(day_sources[day])),
            estimated_cost=None if day in unpriced_days else round(day_costs[day], 6),
            **totals[day],
        )
        for day in sorted(totals)
    ]
    return DailyTrends(days=days, by_model=by_model)

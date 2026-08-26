"""Cost estimation over an editable price table (see pricing.example.json).

Prices are USD per 1M tokens. A model absent from the table is never priced —
it renders tokens-only with a null cost, and the overview total stays null while
any served model is unpriced (a partial total would silently understate spend).
A malformed price file degrades to an empty table rather than failing requests:
a pricing typo must never break the app.
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


class PriceTable(BaseModel):
    version: int = 1
    models: dict[str, ModelPrice] = {}

    @classmethod
    def load(cls, path: Path) -> "PriceTable":
        if not path.exists():
            return cls()
        try:
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return cls()

    def price_for(self, model_id: str) -> ModelPrice | None:
        return self.models.get(model_id)

    def estimate_cost(
        self,
        model_id: str,
        *,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int,
        cache_read_tokens: int,
    ) -> float | None:
        price = self.price_for(model_id)
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
        item.model_id,
        input_tokens=item.input_tokens,
        output_tokens=item.output_tokens,
        cache_creation_tokens=item.cache_creation_tokens,
        cache_read_tokens=item.cache_read_tokens,
    )


def attach_model_costs(models, table: PriceTable):
    return [m.model_copy(update={"estimated_cost_usd": _cost_of(m, table)}) for m in models]


def enrich_overview(overview: Overview, table: PriceTable) -> Overview:
    """Attach per-model costs; the total only appears when every model is priced."""
    by_model = attach_model_costs(overview.by_model, table)
    fully_priced = bool(by_model) and all(m.estimated_cost_usd is not None for m in by_model)
    total = round(sum(m.estimated_cost_usd for m in by_model), 6) if fully_priced else None
    return overview.model_copy(
        update={"by_model": by_model, "estimated_cost_usd": total},
    )


def fold_projects(rows: list[ProjectModelUsage], table: PriceTable) -> ProjectsReport:
    """Fold per-model-per-project rows into project totals.

    Same honesty rule as the daily fold: a project's cost stays null while any
    model contributing to it is unpriced.
    """
    priced_rows = attach_model_costs(rows, table)
    totals: dict[str, dict[str, int]] = {}
    titles: dict[str, str] = {}
    project_costs: dict[str, float] = {}
    unpriced_projects: set[str] = set()
    for row in priced_rows:
        acc = totals.setdefault(row.directory, dict.fromkeys(_SUMMARY_KEYS, 0))
        titles.setdefault(row.directory, row.title)
        for key in _SUMMARY_KEYS:
            acc[key] += getattr(row, key)
        if row.estimated_cost_usd is None:
            unpriced_projects.add(row.directory)
        else:
            project_costs[row.directory] = (
                project_costs.get(row.directory, 0.0) + row.estimated_cost_usd
            )

    projects = [
        ProjectUsage(
            directory=directory,
            title=titles[directory],
            estimated_cost_usd=(
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
    unpriced_days: set[str] = set()
    for row in by_model:
        acc = totals.setdefault(row.day, dict.fromkeys(_SUMMARY_KEYS, 0))
        for key in _SUMMARY_KEYS:
            acc[key] += getattr(row, key)
        if row.estimated_cost_usd is None:
            unpriced_days.add(row.day)
        else:
            day_costs[row.day] = day_costs.get(row.day, 0.0) + row.estimated_cost_usd

    days = [
        DailyUsage(
            day=day,
            estimated_cost_usd=None if day in unpriced_days else round(day_costs[day], 6),
            **totals[day],
        )
        for day in sorted(totals)
    ]
    return DailyTrends(days=days, by_model=by_model)

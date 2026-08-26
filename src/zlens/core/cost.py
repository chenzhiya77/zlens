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

from zlens.sources.models import Overview

_TOKENS_PER_PRICE_UNIT = 1_000_000


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


def enrich_overview(overview: Overview, table: PriceTable) -> Overview:
    """Attach per-model costs; the total only appears when every model is priced."""
    by_model = []
    for item in overview.by_model:
        cost = table.estimate_cost(
            item.model_id,
            input_tokens=item.input_tokens,
            output_tokens=item.output_tokens,
            cache_creation_tokens=item.cache_creation_tokens,
            cache_read_tokens=item.cache_read_tokens,
        )
        by_model.append(item.model_copy(update={"estimated_cost_usd": cost}))

    fully_priced = bool(by_model) and all(m.estimated_cost_usd is not None for m in by_model)
    total = round(sum(m.estimated_cost_usd for m in by_model), 6) if fully_priced else None
    return overview.model_copy(
        update={"by_model": by_model, "estimated_cost_usd": total},
    )

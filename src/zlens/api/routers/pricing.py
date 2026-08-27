"""Price-table read/write endpoints (user-editable pricing.json)."""

import json

from fastapi import APIRouter, Depends, HTTPException

from zlens.api.deps import get_settings
from zlens.core.config import Settings
from zlens.core.cost import PriceTable

router = APIRouter(prefix="/api", tags=["pricing"])

_PRICE_FIELDS = ("input", "output", "cache_read", "cache_write")


@router.get("/pricing", response_model=PriceTable)
def get_pricing(settings: Settings = Depends(get_settings)) -> PriceTable:
    return PriceTable.load(settings.pricing_path)


@router.put("/pricing", response_model=PriceTable)
def put_pricing(
    table: PriceTable,
    settings: Settings = Depends(get_settings),
) -> PriceTable:
    for model_id, price in table.models.items():
        if not model_id.strip():
            raise HTTPException(422, detail="model_id must not be empty")
        for field in _PRICE_FIELDS:
            if getattr(price, field) < 0:
                raise HTTPException(
                    422,
                    detail=f"price for '{model_id}' must not be negative ({field})",
                )
    settings.pricing_path.write_text(
        json.dumps(table.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return PriceTable.load(settings.pricing_path)

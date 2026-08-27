"""Price-table read/write endpoints (user-editable pricing.json)."""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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


class ExtractPayload(BaseModel):
    image_base64: str


_EXTRACT_PROMPT = """\
你是价格表提取助手。从截图表格中提取每个模型的 token 单价。
- 只提取明确的 token 计费单价（input / output / cache read / cache write）；
  套餐、订阅、月费类忽略。
- 输出严格 JSON，不要任何多余文字或 markdown 代码块：
  {"currency":"USD","unit":"per_1M_tokens","models":[
    {"model_id":"模型名","input":数字或null,"output":数字或null,
     "cache_read":数字或null,"cache_write":数字或null}]}
- 若截图标注"每 1k tokens"，换算为每 1M tokens（乘以 1000）；无法换算的字段用 null。
- 截图未写明的字段用 null，不要编造。若图中没有价格表，输出 {"models":[]}。
"""


def _extract_number(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_extract(content: str) -> dict | None:
    text = content.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    models = []
    for item in data.get("models") or []:
        if not isinstance(item, dict):
            continue
        models.append(
            {
                "model_id": str(item.get("model_id") or "").strip(),
                "input": _extract_number(item.get("input")),
                "output": _extract_number(item.get("output")),
                "cache_read": _extract_number(item.get("cache_read")),
                "cache_write": _extract_number(item.get("cache_write")),
            }
        )
    return {
        "currency": str(data.get("currency") or "USD"),
        "unit": str(data.get("unit") or "per_1M_tokens"),
        "models": models,
    }


@router.post("/pricing/extract")
def extract_pricing(
    payload: ExtractPayload,
    settings: Settings = Depends(get_settings),
) -> dict:
    from zlens.core.vlm import VlmCallFailed, VlmUnconfigured, chat

    try:
        content = chat(
            settings,
            text=_EXTRACT_PROMPT,
            image_base64=payload.image_base64,
        )
    except VlmUnconfigured as exc:
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "vlm_unconfigured", "message": str(exc)}},
        )
    except VlmCallFailed as exc:
        return JSONResponse(
            status_code=502,
            content={"error": {"code": "vlm_call_failed", "message": str(exc)}},
        )
    parsed = _parse_extract(content)
    if parsed is None:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "vlm_unparsable",
                    "message": "VLM 返回无法解析，请手动填写价格",
                }
            },
        )
    return parsed

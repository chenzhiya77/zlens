"""Price-table read/write endpoints (user-editable pricing.json)."""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from zlens.api.deps import get_settings
from zlens.core.config import Settings, with_config_overlay
from zlens.core.cost import PriceTable

router = APIRouter(prefix="/api", tags=["pricing"])

_PRICE_FIELDS = ("input", "output", "cache_read", "cache_write")


def _is_channel_key(key: str) -> bool:
    """Price rows address one channel: 'source|provider_id|model_id' (see model_key)."""
    parts = key.split("|")
    return len(parts) == 3 and all(part.strip() for part in parts)


@router.get("/pricing", response_model=PriceTable)
def get_pricing(settings: Settings = Depends(get_settings)) -> PriceTable:
    return PriceTable.load(settings.pricing_path)


@router.put("/pricing", response_model=PriceTable)
def put_pricing(
    table: PriceTable,
    settings: Settings = Depends(get_settings),
) -> PriceTable:
    for key, price in table.models.items():
        if not _is_channel_key(key):
            raise HTTPException(
                422,
                detail=f"价格键「{key}」不是渠道三元组 source|provider_id|model_id，无法对应用量",
            )
        for field in _PRICE_FIELDS:
            if getattr(price, field) < 0:
                raise HTTPException(
                    422,
                    detail=f"渠道「{key}」的价格不能为负数（{field}）",
                )
        # Absent means "not a buyout row"; a value must still be a real amount.
        if price.buyout_amount is not None and price.buyout_amount < 0:
            raise HTTPException(422, detail=f"渠道「{key}」的买断价不能为负数")
    if table.fx_usd_cny is not None and table.fx_usd_cny <= 0:
        raise HTTPException(422, detail="fx_usd_cny 必须是正数（1 美元 = ? 人民币）")
    if table.credit_prices and table.version < 2:
        # credit_prices is the v2 shape: recording one upgrades the file in place
        # (invalid entries were already dropped by the model's own sanitizer —
        # a pricing typo degrades that entry, never the table or the request).
        table = table.model_copy(update={"version": 2})
    settings.pricing_path.write_text(
        json.dumps(table.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return PriceTable.load(settings.pricing_path)


class ExtractPayload(BaseModel):
    image_base64: str
    # Optional: when set, tell the VLM to extract only this model's price
    # (the per-model paste windows in the UI must not touch other rows).
    focus_model: str | None = None


_EXTRACT_PROMPT = """\
你是价格表提取助手。从截图表格中提取每个模型的 token 单价。
- 只提取明确的 token 计费单价（input / output / cache read / cache write）；
  套餐、订阅、月费类忽略。
- 输出严格 JSON，不要任何多余文字或 markdown 代码块：
  {"currency":"CNY"|"USD"|null,"unit":"per_1M_tokens","models":[
    {"model_id":"模型名","input":数字或null,"output":数字或null,
     "cache_read":数字或null,"cache_write":数字或null}]}
- currency 只按截图上真实出现的货币标记判定:¥ / ￥ / CNY / RMB / 人民币 → "CNY";
  $ / USD / 美元 → "USD";截图没有写明币种就输出 null——不要按模型或厂商国籍猜。
- 若截图标注"每 1k tokens"，换算为每 1M tokens（乘以 1000）；无法换算的字段用 null。
- 截图未写明的字段用 null，不要编造。若图中没有价格表，输出 {"models":[]}。
"""


def _prompt_for(focus_model: str | None) -> str:
    prompt = _EXTRACT_PROMPT
    if focus_model:
        prompt += (
            f"\n- 本次只关心模型「{focus_model}」的单价:图中若有多个模型,"
            '只输出该模型的一行;若图中没有该模型,输出 {"models":[]}。'
        )
    return prompt


def _extract_number(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_CNY_MARKS = ("cny", "rmb", "¥", "￥", "人民币")
_USD_MARKS = ("usd", "$", "美元")


def _normalize_currency(value: object) -> str | None:
    """Screenshot currency as 'cny'/'usd', or None when the image never said."""
    text = str(value or "").strip().lower()
    if any(mark in text for mark in _CNY_MARKS):
        return "cny"
    if any(mark in text for mark in _USD_MARKS):
        return "usd"
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
        "currency": _normalize_currency(data.get("currency")),
        "unit": str(data.get("unit") or "per_1M_tokens"),
        "models": models,
    }


@router.post("/pricing/extract")
def extract_pricing(
    payload: ExtractPayload,
    settings: Settings = Depends(get_settings),
) -> dict:
    from zlens.core.vlm import VlmCallFailed, VlmUnconfigured, chat

    # Re-apply the gitignored config file so a save made after server startup
    # is visible to this request (the app snapshot still holds pre-save values).
    settings = with_config_overlay(settings)
    try:
        content = chat(
            settings,
            text=_prompt_for(payload.focus_model),
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

"""VLM settings endpoints (read/save local gitignored config; test connection)."""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from zlens.api.deps import get_settings
from zlens.core.config import Settings
from zlens.core.vlm import VlmCallFailed, VlmUnconfigured, chat

router = APIRouter(prefix="/api", tags=["settings"])


class VlmPayload(BaseModel):
    base_url: str | None = None
    model: str | None = None
    # Empty string means "keep the stored key" — never echo it back.
    api_key: str | None = None


def _read_config(settings: Settings) -> dict:
    path = settings.config_json_path
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_config(settings: Settings, data: dict) -> None:
    settings.config_json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


@router.get("/settings/vlm")
def get_vlm_settings(settings: Settings = Depends(get_settings)) -> dict:
    vlm = _read_config(settings).get("vlm") or {}
    return {
        "base_url": vlm.get("base_url") or settings.vlm_base_url,
        "model": vlm.get("model") or settings.vlm_model,
        "api_key_configured": bool(vlm.get("api_key") or settings.vlm_api_key),
    }


@router.put("/settings/vlm")
def put_vlm_settings(
    payload: VlmPayload,
    settings: Settings = Depends(get_settings),
) -> dict:
    data = _read_config(settings)
    vlm = dict(data.get("vlm") or {})
    if payload.base_url is not None:
        vlm["base_url"] = payload.base_url
    if payload.model is not None:
        vlm["model"] = payload.model
    if payload.api_key:  # non-empty only; empty keeps the stored key
        vlm["api_key"] = payload.api_key
    data["vlm"] = vlm
    _write_config(settings, data)
    return {"ok": True}


@router.post("/settings/vlm/test")
def test_vlm(settings: Settings = Depends(get_settings)) -> dict:
    try:
        reply = chat(settings, text="Reply with exactly: OK")
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
    return {"ok": True, "reply": (reply or "")[:80]}

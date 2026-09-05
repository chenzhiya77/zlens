"""Credit-rates snapshot endpoints (v3 D4) — one user-triggered capture.

The snapshot is display data from client caches: `GET` serves the stored file
(empty state when never captured, not an error) and `POST /credit-rates/capture`
runs the whitelist extraction, writing exactly one gitignored local file. A cache
that exists but cannot be parsed raises `SourceUnavailable`, which the app's
global handler turns into the same 503 {error:{code,message}} shape as sources —
capture never half-writes and never breaks the service.
"""

import json

from fastapi import APIRouter, Depends

from zlens.api.deps import get_settings
from zlens.core.config import Settings
from zlens.core.rates import CreditRatesSnapshot, capture_snapshot

router = APIRouter(prefix="/api", tags=["rates"])


def _load_snapshot(path) -> CreditRatesSnapshot:
    if not path.exists():
        return CreditRatesSnapshot()  # 空态:没抓过,不是错误
    try:
        return CreditRatesSnapshot(**json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
        # 快照损坏降级为空态:一张展示用的缓存文件不能弄坏设置页。
        return CreditRatesSnapshot()


@router.get("/credit-rates", response_model=CreditRatesSnapshot)
def get_credit_rates(settings: Settings = Depends(get_settings)) -> CreditRatesSnapshot:
    return _load_snapshot(settings.credit_rates_path)


@router.post("/credit-rates/capture", response_model=CreditRatesSnapshot)
def capture_credit_rates(settings: Settings = Depends(get_settings)) -> CreditRatesSnapshot:
    snapshot = capture_snapshot(settings.qoder_ide_state_vscdb, settings.trae_cn_state_vscdb)
    settings.credit_rates_path.write_text(
        snapshot.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return snapshot

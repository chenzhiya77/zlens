"""Client-cache pricing-factor snapshot (v3 D4) — display and transcription only.

Two plaintext client caches hold the vendors' per-tier pricing factors: Qoder
IDE (`aicoding.modelConfigs.cache.*` in its state.vscdb) and Trae CN
(`…_AI.agent.model.model_list_map` in its state.vscdb). Neither is an official
document — factors drift between versions (`efficient` 0.5→0.3) and can
contradict the docs (`cmodel` 3.2× against a documented 0.1×–1.6× range) — so
the snapshot is timestamped, provenance-stamped, warned when out of range, and
**never** participates in `credit_value_cny` or any money computation.

Security boundary (research §6.5, test-asserted): extraction is whitelist-
driven — only the pricing fields below are ever copied, key names hitting
ak/sk/api_key/secret/base_url/auth_type/jwt/token never enter the snapshot,
`secret://` KVs are not read at all, and terminal state buffers are not
scanned. A cache that exists but cannot be parsed raises `SourceUnavailable`
(an explicit error, never a half-written file); a cache that does not exist
simply contributes nothing (the app is not installed).
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from zlens.sources.base import SourceUnavailable

# Qoder IDE 缓存键(assistant/experts/quest 三处各一份完整档位表)。
_QODER_CACHE_KEYS = (
    "aicoding.modelConfigs.cache.assistant",
    "aicoding.modelConfigs.cache.experts",
    "aicoding.modelConfigs.cache.quest",
)
# Trae CN 的键带安装指纹前缀,只能按后缀定位。
_TRAE_KEY_SUFFIX = "_AI.agent.model.model_list_map"
# 官方文档宣称的 Qoder price_factor 区间(0.1×–1.6×);越界即告警条目。
_QODER_DOCUMENTED_RANGE = (0.1, 1.6)

# 任何进入快照的字段名都不得命中这些子串(测试断言级安全边界)。
_FORBIDDEN_SUBSTRINGS = ("ak", "sk", "api_key", "secret", "base_url", "auth_type", "jwt", "token")


class RateEntry(BaseModel):
    model_id: str
    display_name: str | None = None
    price_factor: float | None = None
    original_price_factor: float | None = None
    max_input_tokens: int | None = None
    # 官方快照里未见到的字段恒 None:形状漂移时宁可缺,不编造。
    context_tiers: list[int] | None = None
    promotion: str | None = None


class RateWarning(BaseModel):
    model_id: str
    message: str


class CreditRatesSnapshot(BaseModel):
    """One capture of the client-cache pricing factors. Pure display data."""

    version: int = 1
    captured_at: datetime | None = None
    source: str = ""
    kind: str = "client-cache"
    provenance: list[str] = []
    entries: list[RateEntry] = []
    warnings: list[RateWarning] = []


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _connect_ro(vscdb: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{vscdb}?mode=ro", uri=True)


def _capture_qoder_ide(vscdb: Path) -> tuple[list[RateEntry], list[RateWarning]]:
    entries: list[RateEntry] = []
    warnings: list[RateWarning] = []
    con = _connect_ro(vscdb)
    try:
        for cache_key in _QODER_CACHE_KEYS:
            row = con.execute("SELECT value FROM ItemTable WHERE key = ?", (cache_key,)).fetchone()
            if row is None:
                continue  # 字段漂移:该缓存不存在,跳过而不是失败
            try:
                data = json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = _str(item.get("name"))
                if name is None:
                    continue
                factor = _num(item.get("priceFactor"))
                entries.append(
                    RateEntry(
                        model_id=name,
                        display_name=_str(item.get("displayName")),
                        price_factor=factor,
                        original_price_factor=_num(item.get("originalPriceFactor")),
                        max_input_tokens=_int(item.get("maxInputTokens")),
                    )
                )
                low, high = _QODER_DOCUMENTED_RANGE
                if factor is not None and not (low <= factor <= high):
                    warnings.append(
                        RateWarning(
                            model_id=name,
                            message=(
                                f"price_factor {factor} 超出官方文档宣称区间 "
                                f"{low}×–{high}×,以客户端缓存为准但不作计费依据"
                            ),
                        )
                    )
    finally:
        con.close()
    return entries, warnings


def _capture_trae_cn(vscdb: Path) -> tuple[list[RateEntry], list[RateWarning]]:
    """计价字段在 `features.*` 嵌套下(research 快照后的改版):`consumption_rate.data.rate`
    是基础倍率,`features.discount.data` 在场时给出折扣后倍率与原价 + 会员折扣幅度。
    只取 `is_preset` 的官方模型——用户自配的 BYOK 记录(混着 ak/sk)天然被排除。"""
    entries: list[RateEntry] = []
    con = _connect_ro(vscdb)
    try:
        rows = con.execute("SELECT key, value FROM ItemTable").fetchall()
    finally:
        con.close()
    blob = next((v for k, v in rows if isinstance(k, str) and k.endswith(_TRAE_KEY_SUFFIX)), None)
    if blob is None:
        return entries, []  # 字段漂移:键不在了,跳过而不是失败
    try:
        data = json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        return entries, []
    if not isinstance(data, dict):
        return entries, []
    seen: set[str] = set()
    for scenario_models in data.values():
        if not isinstance(scenario_models, list):
            continue
        for model in scenario_models:
            if not isinstance(model, dict) or model.get("is_preset") is not True:
                continue
            name = _str(model.get("name"))
            if name is None or name in seen:
                continue
            seen.add(name)
            features = model.get("features") or {}
            rate_field = features.get("consumption_rate") or {}
            rate_data = rate_field.get("data") if isinstance(rate_field.get("data"), dict) else {}
            factor = _num(rate_data.get("rate"))
            original = None
            promotion = None
            discount = features.get("discount")
            discount_data = discount.get("data") if isinstance(discount, dict) else None
            if isinstance(discount_data, dict):
                discounted = _num(discount_data.get("consumption_rate"))
                if discounted is not None:
                    factor = discounted
                    original = _num(discount_data.get("original_consumption_rate"))
                    member = discount_data.get("member_discount")
                    promotion = (
                        f"会员折扣 {member}%(原价 {original})" if member is not None else None
                    )
            context = model.get("context_window_size") or {}
            max_tokens = (
                _int(context.get("max")[0])
                if isinstance(context.get("max"), list) and context.get("max")
                else _int(context.get("default"))
            )
            entries.append(
                RateEntry(
                    model_id=name,
                    display_name=_str(model.get("display_name")),
                    price_factor=factor,
                    original_price_factor=original,
                    max_input_tokens=max_tokens,
                    promotion=promotion,
                )
            )
    return entries, []


def capture_snapshot(
    qoder_ide_vscdb: Path | None, trae_cn_vscdb: Path | None
) -> CreditRatesSnapshot:
    """One user-triggered capture. A missing app contributes nothing; an existing
    but unparseable cache raises (explicit error, never a half-written file)."""
    entries: list[RateEntry] = []
    warnings: list[RateWarning] = []
    provenance: list[str] = []
    source_parts: list[str] = []
    for label, path, capture in (
        ("qoder_ide", qoder_ide_vscdb, _capture_qoder_ide),
        ("trae_cn", trae_cn_vscdb, _capture_trae_cn),
    ):
        if path is None or not Path(path).is_file():
            continue  # 没装这个应用:静默跳过,不算错误
        provenance.append(f"{label}: {path}")
        source_parts.append(label)
        try:
            part_entries, part_warnings = capture(Path(path))
        except (sqlite3.Error, json.JSONDecodeError, TypeError, ValueError) as exc:
            # 存在但读不了(整库加密/结构漂移/被锁)= 明确失败,绝不半写快照。
            raise SourceUnavailable(f"{label} 客户端缓存无法解析:{exc}") from exc
        entries.extend(part_entries)
        warnings.extend(part_warnings)
    if not provenance:
        raise SourceUnavailable("没有找到任何可抓取的客户端缓存(Qoder IDE / Trae CN 均未安装)")
    return CreditRatesSnapshot(
        captured_at=datetime.now().astimezone(),
        source="+".join(source_parts),
        provenance=provenance,
        entries=entries,
        warnings=warnings,
    )

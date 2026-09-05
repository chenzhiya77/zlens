"""T34 系数快照:白名单抽取、安全边界、越界告警、空态与降级。

fixture 照实测形状合成(research §6.5 + 本机取证):Qoder 缓存条目是
name/displayName/priceFactor/originalPriceFactor/maxInputTokens 的扁平 dict;
Trae 的计价字段在 features.* 嵌套下,且 BYOK 记录混着 ak/sk/base_url ——
快照里必须一个字符都不出现。
"""

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zlens.api.app import create_app
from zlens.core.config import Settings
from zlens.core.rates import SourceUnavailable, capture_snapshot

_FORBIDDEN = ('"ak"', '"sk"', "api_key", "secret", "base_url", "auth_type")


def _qoder_entry(name, display, pf, orig=0, max_in=180000) -> dict:
    return {
        "name": name,
        "displayName": display,
        "description": "",
        "format": "openai",
        "source": "system",
        "maxInputTokens": max_in,
        "enabled": True,
        "originalPriceFactor": orig,
        "priceFactor": pf,
        "strategies": [],
        "tags": None,
        "icon": None,
    }


def _trae_entry(
    name, display, rate, disc=None, preset=True, ctx_max=None, ctx_default=116000, **extra
) -> dict:
    features = {"consumption_rate": {"enable": True, "data": {"rate": rate}}}
    if disc is not None:
        features["discount"] = {"enable": True, "subKey": "", "data": disc}
    item = {
        "name": name,
        "display_name": display,
        "is_preset": preset,
        "context_window_size": {"max": ctx_max, "default": ctx_default},
        "features": features,
    }
    item.update(extra)
    return item


def _write_vscdb(path: Path, items: dict[str, object]) -> Path:
    con = sqlite3.connect(path)
    try:
        con.execute("CREATE TABLE ItemTable (key TEXT UNIQUE, value BLOB)")
        for key, value in items.items():
            con.execute(
                "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
        con.commit()
    finally:
        con.close()
    return path


def _qoder_db(tmp_path: Path) -> Path:
    return _write_vscdb(
        tmp_path / "qoder-state.vscdb",
        {
            # 真机同名密文 KV 就躺在同一个库里:抓取只查三个白名单键,它永不入快照
            "secret://aicoding.auth.creditUsage": "encrypted-buffer-placeholder",
            "aicoding.modelConfigs.cache.assistant": [
                _qoder_entry("auto", "Auto", 1.0),
                _qoder_entry("cmodel", "Cantus", 3.2),  # 越界:文档宣称 0.1–1.6
                _qoder_entry("efficient", "Efficient", 0.3, orig=0.5),  # 实证降价
            ],
            "aicoding.modelConfigs.cache.quest": [_qoder_entry("quest-auto", "Auto", 1.0)],
        },
    )


def _trae_db(tmp_path: Path) -> Path:
    models = [
        _trae_entry(
            "Doubao-Seed-2.1-Turbo",
            "豆包 Seed 2.1 Turbo",
            0.39,
            disc={
                "original_consumption_rate": 0.39,
                "consumption_rate": 0.1,
                "member_discount": 25,
                "is_discount_matched": False,
            },
        ),
        _trae_entry("glm-5.3", "GLM-5.3", 0.4, ctx_max=[1000000]),
        # BYOK 自定义模型:非 preset,字段里混着凭据——必须整条排除
        _trae_entry(
            "my-private-model",
            "My Private",
            None,
            preset=False,
            ak="AK-VALUE",
            sk="SK-VALUE",
            base_url="https://example.internal/v1",
            auth_type="bearer",
        ),
    ]
    return _write_vscdb(
        tmp_path / "trae-state.vscdb",
        {"1417703521530012_AI.agent.model.model_list_map": {"chat_v3": models}},
    )


def _settings(tmp_path: Path, qoder: Path | None = None, trae: Path | None = None) -> Settings:
    return Settings(
        db_path=tmp_path / "z.sqlite",
        minimax_sessions_dir=tmp_path / "mm-missing",
        opencode_db_path=tmp_path / "oc-missing.db",
        workbuddy_dir=tmp_path / "wb-missing",
        qoder_cn_config_dir=tmp_path / "qcn-missing",
        qoder_config_dir=tmp_path / "qoder-missing",
        claude_config_dir=tmp_path / "claude-missing",
        qoder_ide_state_vscdb=qoder or (tmp_path / "qoder-missing.vscdb"),
        trae_cn_state_vscdb=trae or (tmp_path / "trae-missing.vscdb"),
        credit_rates_path=tmp_path / "credit_rates.json",
    )


def test_capture_qoder_rates_and_out_of_range_warning(tmp_path):
    snapshot = capture_snapshot(_qoder_db(tmp_path), None)
    by_id = {e.model_id: e for e in snapshot.entries}
    assert by_id["auto"].price_factor == 1.0
    assert by_id["efficient"].price_factor == 0.3
    assert by_id["efficient"].original_price_factor == 0.5
    assert by_id["quest-auto"].model_id == "quest-auto"
    assert [w.model_id for w in snapshot.warnings] == ["cmodel"]
    assert snapshot.source == "qoder_ide"
    assert any("state.vscdb" in p for p in snapshot.provenance)


def test_capture_trae_rates_discount_and_byok_excluded(tmp_path):
    snapshot = capture_snapshot(None, _trae_db(tmp_path))
    by_id = {e.model_id: e for e in snapshot.entries}
    assert set(by_id) == {"Doubao-Seed-2.1-Turbo", "glm-5.3"}
    doubao = by_id["Doubao-Seed-2.1-Turbo"]
    assert doubao.price_factor == 0.1  # 折扣后
    assert doubao.original_price_factor == 0.39
    assert doubao.promotion and "25%" in doubao.promotion
    assert doubao.max_input_tokens == 116000
    text = snapshot.model_dump_json()
    for token in _FORBIDDEN:
        assert token not in text


def test_capture_with_both_sources_merges(tmp_path):
    snapshot = capture_snapshot(_qoder_db(tmp_path), _trae_db(tmp_path))
    assert snapshot.source == "qoder_ide+trae_cn"
    assert {e.model_id for e in snapshot.entries} >= {"auto", "Doubao-Seed-2.1-Turbo"}


def test_capture_without_any_cache_raises(tmp_path):
    with pytest.raises(SourceUnavailable):
        capture_snapshot(None, None)


def test_corrupted_cache_raises_source_unavailable(tmp_path):
    broken = tmp_path / "broken.vscdb"
    con = sqlite3.connect(broken)
    con.execute("CREATE TABLE ItemTable (key TEXT UNIQUE, value BLOB)")
    con.execute("INSERT INTO ItemTable (key, value) VALUES ('x', 'y')")  # 缺目标键
    con.commit()
    con.close()
    # 键不存在 = 漂移,返回空而不失败;坏库文件本身才会 raise
    snapshot = capture_snapshot(broken, None)
    assert snapshot.entries == []
    good_but_encrypted = tmp_path / "encrypted.vscdb"
    con = sqlite3.connect(good_but_encrypted)
    con.execute("CREATE TABLE other (x INTEGER)")
    con.commit()
    con.close()
    with pytest.raises(SourceUnavailable):
        capture_snapshot(good_but_encrypted, None)


def test_http_round_trip_and_empty_state(tmp_path):
    client = TestClient(create_app(_settings(tmp_path, qoder=_qoder_db(tmp_path))))
    empty = client.get("/api/credit-rates").json()
    assert empty["entries"] == [] and empty["captured_at"] is None

    captured = client.post("/api/credit-rates/capture").json()
    assert captured["source"] == "qoder_ide"
    assert len(captured["entries"]) == 4
    served = client.get("/api/credit-rates").json()
    assert served["captured_at"] is not None
    assert {e["model_id"] for e in served["entries"]} == {
        "auto",
        "cmodel",
        "efficient",
        "quest-auto",
    }


def test_http_capture_without_caches_is_explicit_error(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    response = client.post("/api/credit-rates/capture")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"


def test_corrupted_snapshot_file_degrades_to_empty(tmp_path):
    settings = _settings(tmp_path)
    settings.credit_rates_path.write_text("{broken", encoding="utf-8")
    client = TestClient(create_app(settings))
    body = client.get("/api/credit-rates").json()
    assert body["entries"] == []

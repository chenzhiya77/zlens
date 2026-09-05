"""International Qoder adapter(v3 T37):与 qoder_cn 同构、独立 source id。

取证(research 2026-09-05):~/.qoder 与 ~/.qoder-cn 的 request_id 零交集,
是两条独立的计费流,不存在双写;积分语义与分源设计一致。
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zlens.api.app import create_app
from zlens.core.config import Settings
from zlens.sources.qoder import QoderSource


def _settings(make_qoder_cn, records, tmp_path, last_cleanup=False) -> Settings:
    root = make_qoder_cn(
        [{"project_slug": "E--app-proj-a", "session_id": "s1", "records": records}],
        last_cleanup=last_cleanup,
        root_name="qoder",
    )
    return Settings(
        db_path=tmp_path / "z.sqlite",
        minimax_sessions_dir=tmp_path / "mm-missing",
        opencode_db_path=tmp_path / "oc-missing.db",
        workbuddy_dir=tmp_path / "wb-missing",
        qoder_cn_config_dir=tmp_path / "qoder-cn-missing",
        qoder_config_dir=root,
        pricing_path=tmp_path / "pricing.json",
    )


def _record(request_id="r-1", credits=1.25, ts="2026-09-01T12:00:00.000Z") -> dict:
    return {
        "type": "assistant",
        "role": "assistant",
        "timestamp": ts,
        "cwd": "E:\\app\\proj-a",
        "entrypoint": "cli",
        "sessionId": "s1",
        "message": {
            "id": f"am-{request_id}",
            "role": "assistant",
            "model": "qmodel_38max",
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "request_id": request_id,
                "billable": True,
                "credits": credits,
                "original_credits": credits,
            },
        },
    }


def test_intl_qoder_meters_credits_with_separate_identity(make_qoder_cn, tmp_path):
    client = TestClient(create_app(_settings(make_qoder_cn, [_record()], tmp_path)))
    body = client.get("/api/overview", params={"source": "qoder"}).json()
    row = body["by_model"][0]
    assert (row["source"], row["provider_id"], row["model_id"]) == (
        "qoder",
        "qoder",
        "qmodel_38max",
    )
    assert row["credits"] == 1.25
    assert row["tokens_reported"] is False
    assert row["estimated_cost"] is None
    meta = client.get("/api/meta", params={"source": "qoder"}).json()
    assert meta["credit_reporting_sources"] == ["qoder"]
    assert meta["unpriced_credits"] == ["qoder"]


def test_intl_retention_hint_text_differs_from_cn(make_qoder_cn, tmp_path):
    client = TestClient(
        create_app(_settings(make_qoder_cn, [_record()], tmp_path, last_cleanup=True))
    )
    meta = client.get("/api/meta", params={"source": "qoder"}).json()
    assert meta["retention_hint"]
    assert "Qoder CN" not in meta["retention_hint"]


def test_qoder_and_qoder_cn_are_distinct_sources(make_qoder_cn, tmp_path):
    settings = _settings(make_qoder_cn, [_record()], tmp_path)
    settings = Settings(
        **{
            **settings.model_dump(),
            "qoder_config_dir": make_qoder_cn(
                [{"project_slug": "E--app-proj-a", "session_id": "s1", "records": [_record()]}],
                root_name="qoder",
            ),
            "qoder_cn_config_dir": tmp_path / "qoder-cn-missing",
        }
    )
    client = TestClient(create_app(settings))
    meta = client.get("/api/meta").json()
    ids = [s["id"] for s in meta["sources"]]
    assert "qoder" in ids and "qoder_cn" in ids


def test_source_missing_degrades_to_unavailable(client_factory):
    client = client_factory(rows=[{"model_id": "m1", "computed_total_tokens": 1}])
    response = client.get("/api/overview", params={"source": "qoder"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"


@pytest.mark.live
def test_live_qoder_intl_real_local_data():
    root = Path.home() / ".qoder"
    if not (root / "projects").is_dir():
        pytest.skip("no real ~/.qoder on this machine")
    source = QoderSource(root)
    body = source.overview()
    assert body.request_count > 300
    assert body.credits is not None and body.credits > 1000
    assert body.total_tokens == 0
    assert body.tokens_reported is False
    assert "qmodel_38max" in {m.model_id for m in body.by_model}

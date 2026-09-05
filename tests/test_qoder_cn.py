"""Qoder CN 适配器(v3 T33):积分账 + token 未上报 + 入口闸门 + 子代理 + 30 天清理提示。

fixture 照真实形状写(research §8):Claude Code 形信封(timestamp 为 ISO Z 字符串、
entrypoint/cwd/gitBranch 在顶层)、usage 挂在 message.usage(credits 可到 9 位小数)、
token 四档恒 0、子代理 transcript 在 <sessionId>/subagents/ 下。
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zlens.api.app import create_app
from zlens.core.config import Settings
from zlens.sources.qoder_cn import QoderCnSource
from zlens.sources.timeutil import iso_to_epoch_ms, ms_to_local_day

_MISSING = object()
_TS_DAY1 = "2026-09-01T12:00:00.000Z"
_TS_DAY2 = "2026-09-02T12:00:00.000Z"


def _record(
    cwd="E:\\app\\proj-a",
    ts=_TS_DAY1,
    model="qfmodel",
    entrypoint="cli",
    credits=0.794388331,
    original=_MISSING,
    billable=True,
    request_id="r-1",
    synthetic=False,
) -> dict:
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "context_usage_ratio": 0.1,
        "iterations": 1,
        "request_id": request_id,
        "billable": billable,
    }
    if credits is not _MISSING:
        usage["credits"] = credits
    if original is not _MISSING:
        usage["original_credits"] = original
    return {
        "type": "assistant",
        "role": "assistant",
        "timestamp": ts,
        "cwd": cwd,
        "entrypoint": entrypoint,
        "gitBranch": "main",
        "isSidechain": False,
        "sessionId": "s1",
        "uuid": f"u-{request_id}",
        "version": "1.1.31",
        "message": {
            "id": f"am-{request_id}",
            "type": "message",
            "role": "assistant",
            "model": "<synthetic>" if synthetic else model,
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "content": [{"type": "output_text", "text": "ok"}],
            "usage": usage,
        },
    }


def _spec(records, session_id="s1", project_slug="E--app-proj-a", subagents=None) -> dict:
    spec = {"project_slug": project_slug, "session_id": session_id, "records": records}
    if subagents:
        spec["subagents"] = subagents
    return spec


def test_overview_credits_with_tokens_reported_false(client_factory, make_qoder_cn):
    client = client_factory(
        qoder_cn=[
            _spec(
                [
                    _record(request_id="r-1", credits=0.794388331, ts=_TS_DAY1),
                    _record(request_id="r-2", credits=0.855711087, ts=_TS_DAY2),
                ]
            )
        ]
    )
    body = client.get("/api/overview", params={"source": "qoder_cn"}).json()
    row = body["by_model"][0]
    assert (row["source"], row["provider_id"], row["model_id"]) == ("qoder_cn", "qoder", "qfmodel")
    assert row["request_count"] == 2
    # token 四档恒 0 是占位:tokens_reported=False,行级也永不乘价
    assert row["total_tokens"] == 0
    assert row["tokens_reported"] is False
    assert row["credits_reported"] is True
    assert row["estimated_cost"] is None
    # 9 位小数逐条原始浮点求和,仅聚合层取 6 位
    assert row["credits"] == pytest.approx(1.650099418, abs=1e-6)
    assert body["credits"] == pytest.approx(1.650099418, abs=1e-6)
    assert body["original_credits"] is None
    assert body["tokens_reported"] is False
    assert body["credit_reporting_sources"] == ["qoder_cn"]
    assert body["token_reporting_sources"] == []


def test_original_credits_kept_per_row(client_factory, make_qoder_cn):
    client = client_factory(
        qoder_cn=[_spec([_record(request_id="r-1", credits=0.5, original=1.0)])]
    )
    body = client.get("/api/overview", params={"source": "qoder_cn"}).json()
    row = body["by_model"][0]
    assert row["credits"] == 0.5
    assert row["original_credits"] == 1.0
    assert body["credits"] == 0.5
    assert body["original_credits"] == 1.0


def test_billable_false_counts_request_not_credits(client_factory, make_qoder_cn):
    client = client_factory(
        qoder_cn=[_spec([_record(request_id="r-1", credits=0.9, original=0.9, billable=False)])]
    )
    body = client.get("/api/overview", params={"source": "qoder_cn"}).json()
    row = body["by_model"][0]
    assert row["request_count"] == 1
    assert row["credits"] is None
    assert row["original_credits"] is None


def test_synthetic_and_ide_entrypoint_skipped(client_factory, make_qoder_cn):
    client = client_factory(
        qoder_cn=[
            _spec(
                [
                    _record(request_id="r-1", credits=0.5),
                    # 合成错误记录:不是模型调用
                    _record(request_id="r-2", credits=0.5, synthetic=True),
                    # IDE 写入的记录:被入口闸门挡住(防未来双写重复计量)
                    _record(request_id="r-3", credits=0.5, entrypoint="ide"),
                ]
            )
        ]
    )
    body = client.get("/api/overview", params={"source": "qoder_cn"}).json()
    row = body["by_model"][0]
    assert row["request_count"] == 1
    assert row["credits"] == 0.5


def test_credits_missing_stays_null_zero_stays_zero(client_factory, make_qoder_cn):
    client = client_factory(
        qoder_cn=[
            _spec(
                [
                    # 字段缺失 → null(绝不当 0)
                    _record(model="qfmodel", request_id="r-1", credits=_MISSING),
                    # 字段在值、值为 0 → 真 0
                    _record(model="qmodel_38max", request_id="r-2", credits=0.0),
                ]
            )
        ]
    )
    body = client.get("/api/overview", params={"source": "qoder_cn"}).json()
    credits = {m["model_id"]: m["credits"] for m in body["by_model"]}
    assert credits["qfmodel"] is None
    assert credits["qmodel_38max"] == 0.0
    # 合计只含在值的 0:0.0(不是 None,也不是 0.79)
    assert body["credits"] == 0.0


def test_subagents_included_and_request_id_deduped(client_factory, make_qoder_cn):
    client = client_factory(
        qoder_cn=[
            _spec(
                [
                    _record(request_id="r-main", credits=1.0),
                ],
                subagents=[
                    {
                        "name": "agent-aExplore-ef7c.jsonl",
                        "records": [
                            # 独立计费的子代理调用
                            _record(request_id="r-sub", credits=0.4),
                            # 与主会话相同的 request_id:重放,不重复计费
                            _record(request_id="r-main", credits=1.0),
                        ],
                    }
                ],
            )
        ]
    )
    body = client.get("/api/overview", params={"source": "qoder_cn"}).json()
    row = body["by_model"][0]
    assert row["request_count"] == 2
    assert row["credits"] == 1.4


def test_day_cut_and_window_filter(client_factory, make_qoder_cn):
    client = client_factory(
        qoder_cn=[
            _spec(
                [
                    _record(request_id="r-1", credits=1.0, ts=_TS_DAY1),
                    _record(request_id="r-2", credits=2.0, ts=_TS_DAY2),
                ]
            )
        ]
    )
    # 期望日由适配器同一条 ISO→本地日转换推导,对时区稳健
    day1 = ms_to_local_day(iso_to_epoch_ms(_TS_DAY1))
    day2 = ms_to_local_day(iso_to_epoch_ms(_TS_DAY2))
    assert day1 != day2
    trends = client.get("/api/trends/daily", params={"source": "qoder_cn"}).json()
    by_day = {d["day"]: d for d in trends["days"]}
    assert sorted(by_day) == [day1, day2]
    assert by_day[day1]["credits"] == 1.0
    windowed = client.get(
        "/api/trends/daily",
        params={"source": "qoder_cn", "start": day1, "end": day1},
    ).json()
    assert [d["day"] for d in windowed["days"]] == [day1]
    assert windowed["days"][0]["request_count"] == 1


def test_retention_hint_from_last_cleanup_marker(make_qoder_cn, tmp_path):
    root = make_qoder_cn([_spec([_record()])], last_cleanup=True)

    def _client() -> TestClient:
        return TestClient(
            create_app(
                Settings(
                    db_path=tmp_path / "z.sqlite",
                    minimax_sessions_dir=tmp_path / "mm-missing",
                    opencode_db_path=tmp_path / "oc-missing.db",
                    workbuddy_dir=tmp_path / "wb-missing",
                    qoder_cn_config_dir=root,
                    pricing_path=tmp_path / "pricing.json",
                )
            )
        )

    meta = _client().get("/api/meta", params={"source": "qoder_cn"}).json()
    assert meta["retention_hint"] and "30" in meta["retention_hint"]
    # 标记消失(如官方清理策略变化)→ 提示随之消失,不残留
    (root / ".last-cleanup").unlink()
    meta_plain = _client().get("/api/meta", params={"source": "qoder_cn"}).json()
    assert meta_plain["retention_hint"] is None


def test_projects_view_groups_by_cwd(client_factory, make_qoder_cn):
    client = client_factory(
        qoder_cn=[
            _spec(
                [
                    _record(request_id="r-1", credits=1.0, cwd="E:\\app\\proj-a"),
                    _record(request_id="r-2", credits=2.0, cwd="E:\\app\\proj-b"),
                ]
            )
        ]
    )
    projects = client.get("/api/projects", params={"source": "qoder_cn"}).json()["projects"]
    assert {p["directory"] for p in projects} == {"E:\\app\\proj-a", "E:\\app\\proj-b"}
    assert all(p["tokens_reported"] is False for p in projects)
    assert sum(p["credits"] for p in projects) == pytest.approx(3.0, abs=1e-9)


def test_damaged_lines_skipped(make_qoder_cn):
    root = make_qoder_cn([_spec([_record(request_id="r-1", credits=1.0)])])
    transcript = root / "projects" / "E--app-proj-a" / "s1.jsonl"
    transcript.write_text(
        "{broken json\n" + transcript.read_text(encoding="utf-8"), encoding="utf-8"
    )
    body = QoderCnSource(root).overview()
    assert body.request_count == 1
    assert body.credits == 1.0


def test_source_missing_degrades_to_unavailable(client_factory):
    client = client_factory(rows=[{"model_id": "m1", "computed_total_tokens": 1}])
    meta = client.get("/api/meta").json()
    ref = next(s for s in meta["sources"] if s["id"] == "qoder_cn")
    assert ref["available"] is False
    assert ref["error"]
    response = client.get("/api/overview", params={"source": "qoder_cn"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"


@pytest.mark.live
def test_live_qoder_cn_real_local_data():
    root = Path.home() / ".qoder-cn"
    if not (root / "projects").is_dir():
        pytest.skip("no real ~/.qoder-cn on this machine")
    source = QoderCnSource(root)
    body = source.overview()
    assert body.request_count > 300
    assert body.credits is not None and body.credits > 100
    assert body.total_tokens == 0
    assert body.tokens_reported is False
    assert "qfmodel" in {m.model_id for m in body.by_model}
    assert ("qoder", "qfmodel") in {(m.provider_id, m.model_id) for m in body.by_model}

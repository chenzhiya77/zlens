"""T38 Claude Code 适配器:流式去重(按 message.id 取四档合计最大)、四档真数、保留期提示。

fixture 照实测形状写:信封 type=assistant、message.usage 四档互斥且无 total 字段、
流式重复分两种形态(逐位重放 / 全零占位 + 真用量)、模型名可含斜杠、子代理在
<sessionId>/subagents/ 下、.last-cleanup 标记保留期。
"""

import json
from pathlib import Path

import pytest

from zlens.sources.claude import ClaudeSource
from zlens.sources.timeutil import iso_to_epoch_ms, ms_to_local_day

_TS1 = "2026-09-01T12:00:00.000Z"
_TS2 = "2026-09-02T12:00:00.000Z"


def _usage(input_tokens=100, output_tokens=50, cache_write=10, cache_read=40, thinking=5) -> dict:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_write,
        "cache_read_input_tokens": cache_read,
        "output_tokens_details": {"reasoning_tokens": thinking},
    }


def _record(
    cwd="E:\\app\\proj-a",
    ts=_TS1,
    model="stealth/ox-alpha",
    usage=None,
    message_id="m-1",
    synthetic=False,
) -> dict:
    if usage is None:
        usage = _usage()
    return {
        "type": "assistant",
        "timestamp": ts,
        "cwd": cwd,
        "sessionId": "s1",
        "entrypoint": "cli",
        "gitBranch": "main",
        "isSidechain": False,
        "uuid": f"u-{message_id}",
        "message": {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "model": "<synthetic>" if synthetic else model,
            "usage": usage,
        },
    }


def _spec(records, session_id="s1", project_slug="E--app-proj-a", subagents=None) -> dict:
    spec = {"project_slug": project_slug, "session_id": session_id, "records": records}
    if subagents:
        spec["subagents"] = subagents
    return spec


def test_dedup_takes_largest_usage_per_message_id(client_factory):
    client = client_factory(
        claude=[
            {
                "project_slug": "E--app-proj-a",
                "session_id": "s1",
                "records": [
                    # 形态①:逐位相同的重放 → 只计一次
                    _record(message_id="m-1", usage=_usage(input_tokens=100)),
                    _record(message_id="m-1", usage=_usage(input_tokens=100)),
                    # 形态②:全零占位事件 + 一条真用量 → 只计真用量
                    _record(
                        message_id="m-2",
                        usage={"input_tokens": 0, "output_tokens": 0},
                    ),
                    _record(
                        message_id="m-2",
                        usage={"input_tokens": 0, "output_tokens": 0},
                    ),
                    _record(
                        message_id="m-2",
                        ts=_TS1,
                        usage={
                            "input_tokens": 537,
                            "output_tokens": 337,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 12544,
                            "output_tokens_details": {"reasoning_tokens": 0},
                        },
                    ),
                ],
            }
        ]
    )
    body = client.get("/api/overview", params={"source": "claude"}).json()
    assert body["request_count"] == 2  # 两个 message.id,不是 5 条事件
    model = body["by_model"][0]
    assert model["input_tokens"] == 100 + 537
    assert model["output_tokens"] == 50 + 337
    assert model["cache_read_tokens"] == 40 + 12544
    # 契约恒等式:四档相加 == total(上游无 total 字段)
    assert model["total_tokens"] == (
        model["input_tokens"]
        + model["output_tokens"]
        + model["cache_creation_tokens"]
        + model["cache_read_tokens"]
    )


def test_tier_split_and_credits_absent(client_factory):
    client = client_factory(claude=[_spec([_record()])])
    body = client.get("/api/overview", params={"source": "claude"}).json()
    row = body["by_model"][0]
    assert (row["source"], row["provider_id"], row["model_id"]) == (
        "claude",
        "claude",
        "stealth/ox-alpha",
    )
    assert row["input_tokens"] == 100
    assert row["output_tokens"] == 50
    assert row["cache_creation_tokens"] == 10
    assert row["cache_read_tokens"] == 40
    assert row["reasoning_tokens"] == 5
    assert row["tokens_reported"] is True
    # 无积分账:credits 恒 null、credits_reported False,聚合里也不出现第三笔
    assert row["credits"] is None
    assert row["credits_reported"] is False
    assert body["credits"] is None
    assert body["credit_reporting_sources"] == []
    # 未计价渠道:行级 null cost、聚合按 ¥0 直接给出
    assert row["estimated_cost"] is None
    assert body["estimated_cost"] == 0.0


def test_synthetic_skipped_and_model_with_slash_kept(client_factory):
    client = client_factory(
        claude=[
            _spec(
                [
                    _record(message_id="m-ok", model="stealth/ox-alpha", usage=_usage()),
                    _record(message_id="m-syn", model="<synthetic>", usage=_usage(input_tokens=9)),
                ]
            )
        ]
    )
    body = client.get("/api/overview", params={"source": "claude"}).json()
    assert [m["model_id"] for m in body["by_model"]] == ["stealth/ox-alpha"]
    keys = client.get("/api/meta", params={"source": "claude"}).json()
    assert keys["source_id"] == "claude"


def test_subagents_included(client_factory):
    client = client_factory(
        claude=[
            _spec(
                [_record(message_id="m-main", usage=_usage(input_tokens=100))],
                subagents=[
                    {
                        "name": "agent-a1.jsonl",
                        "records": [_record(message_id="m-sub", usage=_usage(input_tokens=200))],
                    }
                ],
            )
        ]
    )
    body = client.get("/api/overview", params={"source": "claude"}).json()
    assert body["request_count"] == 2
    assert body["total_tokens"] == 200 + 300  # 主会话 200 + 子代理 300


def test_damaged_lines_skipped(make_qoder_cn, tmp_path):
    root = make_qoder_cn([_spec([_record(message_id="m-1", usage=_usage())])], root_name="claude")
    transcript = root / "projects" / "E--app-proj-a" / "s1.jsonl"
    transcript.write_text(
        "{broken json\n" + transcript.read_text(encoding="utf-8"), encoding="utf-8"
    )
    body = ClaudeSource(root).overview()
    assert body.request_count == 1
    assert body.total_tokens == 200


def test_day_cut_and_window_filter(client_factory):
    client = client_factory(
        claude=[
            _spec(
                [
                    _record(message_id="m-1", ts=_TS1, usage=_usage(input_tokens=100)),
                    _record(message_id="m-2", ts=_TS2, usage=_usage(input_tokens=300)),
                ]
            )
        ]
    )
    day1 = ms_to_local_day(iso_to_epoch_ms(_TS1))
    day2 = ms_to_local_day(iso_to_epoch_ms(_TS2))
    trends = client.get("/api/trends/daily", params={"source": "claude"}).json()
    by_day = {d["day"]: d for d in trends["days"]}
    assert sorted(by_day) == [day1, day2]
    windowed = client.get(
        "/api/trends/daily", params={"source": "claude", "start": day1, "end": day1}
    ).json()
    assert [d["day"] for d in windowed["days"]] == [day1]
    assert windowed["days"][0]["request_count"] == 1


def test_retention_hint_from_last_cleanup_marker(client_factory):
    client = client_factory(claude=[_spec([_record()])], claude_last_cleanup=True)
    meta = client.get("/api/meta", params={"source": "claude"}).json()
    assert meta["retention_hint"] and "30" in meta["retention_hint"]
    # token 来源:不出现在「未计入 token 口径」提示,出现在 token_reporting_sources
    assert meta["token_reporting_sources"] == ["claude"]
    assert meta["credit_reporting_sources"] == []


def test_projects_groups_by_cwd(client_factory):
    client = client_factory(
        claude=[
            _spec(
                [
                    _record(message_id="m-1", cwd="E:\\app\\proj-a", usage=_usage()),
                    _record(message_id="m-2", cwd="E:\\app\\proj-b", usage=_usage()),
                ]
            )
        ]
    )
    projects = client.get("/api/projects", params={"source": "claude"}).json()["projects"]
    assert {p["directory"] for p in projects} == {"E:\\app\\proj-a", "E:\\app\\proj-b"}
    assert all(p["total_tokens"] == 200 for p in projects)


def test_source_missing_degrades_to_unavailable(client_factory):
    client = client_factory(rows=[{"model_id": "m1", "computed_total_tokens": 1}])
    meta = client.get("/api/meta").json()
    ref = next(s for s in meta["sources"] if s["id"] == "claude")
    assert ref["available"] is False
    assert ref["error"]
    response = client.get("/api/overview", params={"source": "claude"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"


@pytest.mark.live
def test_live_claude_real_local_data():
    root = Path.home() / ".claude"
    if not (root / "projects").is_dir():
        pytest.skip("no real ~/.claude on this machine")
    # 原始 usage 行数(不去重)——去重后的计费调用必须严格小于它
    raw_rows = 0
    for f in root.rglob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("type") != "assistant":
                continue
            u = (e.get("message") or {}).get("usage")
            if isinstance(u, dict) and u:
                raw_rows += 1
    body = ClaudeSource(root).overview()
    assert body.request_count > 50
    assert body.request_count < raw_rows  # 去重生效:流式重放/占位被压缩
    assert body.total_tokens > 1_000_000
    for m in body.by_model:
        assert (
            m.input_tokens + m.output_tokens + m.cache_creation_tokens + m.cache_read_tokens
            == m.total_tokens
        )

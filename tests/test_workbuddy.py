"""WorkBuddy 适配器(v3 T32):嵌套拆档、credits null-vs-0、双写不重复计量。

fixture 照真实形状写(research §6.3/§9):type=message + role=assistant + providerData.rawUsage
三方言并存、hit/write 嵌在 prompt 内、credit 可为真 0(混元免费)或缺失。
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zlens.api.app import create_app
from zlens.core.config import Settings
from zlens.sources.timeutil import ms_to_local_day
from zlens.sources.workbuddy import WorkbuddySource

_MISSING = object()
_MS_DAY1 = 1_788_000_000_000
_MS_DAY2 = _MS_DAY1 + 86_400_000


def _record(
    session_id="s1",
    cwd="E:/app/proj-a",
    ms=_MS_DAY1,
    model="glm-5.2",
    tier="auto",
    prompt=100,
    hit=0,
    write=0,
    completion=50,
    thinking=0,
    credit=_MISSING,
    message_id=None,
) -> dict:
    raw = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "prompt_cache_hit_tokens": hit,
        "prompt_cache_miss_tokens": prompt - hit,
        "prompt_cache_write_tokens": write,
        "prompt_tokens_details": {"cached_tokens": hit},
        "completion_tokens_details": {"reasoning_tokens": thinking},
        # 上游 total = prompt + completion(恒等式见 research §6.3)
        "total_tokens": prompt + completion,
    }
    if credit is not _MISSING:
        raw["credit"] = credit
    mid = message_id or f"msg-{model}-{ms}-{prompt}-{completion}"
    return {
        "type": "message",
        "role": "assistant",
        "timestamp": ms,
        "cwd": cwd,
        "sessionId": session_id,
        "id": mid,
        "content": [{"type": "output_text", "text": "ok"}],
        "providerData": {
            "messageId": mid,
            "conversationRequestId": f"conv-{mid}",
            "traceId": "0" * 32,
            "model": model,
            "requestModelId": tier,
            "rawUsage": raw,
        },
    }


def _settings(make_workbuddy, sessions, workbuddy_usage=(), pricing=None) -> Settings:
    root = make_workbuddy(sessions, workbuddy_usage)
    payload = {"version": 1, "models": {}}
    if pricing is not None:
        payload.update(pricing)
    pricing_path = Path(root) / "pricing.json"
    pricing_path.write_text(json.dumps(payload), encoding="utf-8")
    return Settings(
        db_path=Path(root) / "unused-zcode.sqlite",
        minimax_sessions_dir=Path(root) / "minimax-missing",
        opencode_db_path=Path(root) / "opencode-missing.db",
        workbuddy_dir=root,
        pricing_path=pricing_path,
    )


def test_overview_splits_nested_tiers_and_sums_credits(client_factory, make_workbuddy):
    client = client_factory(
        workbuddy=[
            {
                "project_slug": "e--app-proj-a",
                "session_id": "s1",
                "records": [
                    _record(
                        ms=_MS_DAY1,
                        prompt=100,
                        hit=60,
                        write=20,
                        completion=50,
                        thinking=10,
                        credit=3.81,
                    ),
                    _record(message_id="msg-2", ms=_MS_DAY2, prompt=200, completion=30, credit=0.5),
                ],
            }
        ]
    )
    body = client.get("/api/overview", params={"source": "workbuddy"}).json()
    row = body["by_model"][0]
    assert (row["source"], row["provider_id"], row["model_id"]) == ("workbuddy", "auto", "glm-5.2")
    assert row["request_count"] == 2
    # 拆档:hit 与 write 都嵌在 prompt 内,input = prompt − hit − write
    assert row["input_tokens"] == (100 - 60 - 20) + 200
    assert row["cache_read_tokens"] == 60
    assert row["cache_creation_tokens"] == 20
    assert row["output_tokens"] == 80
    assert row["reasoning_tokens"] == 10
    # 契约恒等式:四档相加 == total
    assert row["total_tokens"] == (
        row["input_tokens"]
        + row["output_tokens"]
        + row["cache_creation_tokens"]
        + row["cache_read_tokens"]
    )
    assert row["credits"] == 4.31
    assert row["credits_reported"] is True
    assert row["tokens_reported"] is True
    # 未计价渠道:行级 null cost,聚合按 ¥0 直接给出
    assert row["estimated_cost"] is None
    assert body["estimated_cost"] == 0.0
    assert body["credit_total"] == 4.31


def test_tier_and_real_model_are_separate_channels(client_factory, make_workbuddy):
    client = client_factory(
        workbuddy=[
            {
                "project_slug": "e--app-proj-a",
                "session_id": "s1",
                "records": [
                    # 同档位(auto)解析到不同真实模型 → 分行
                    _record(model="glm-5.2", ms=_MS_DAY1),
                    _record(model="glm-5.3", message_id="msg-b", ms=_MS_DAY1),
                    # 同真实模型、不同档位 → 也分行(跨渠道不合并)
                    _record(model="glm-5.2", tier="glm-5.2", message_id="msg-c", ms=_MS_DAY1),
                ],
            }
        ]
    )
    body = client.get("/api/overview", params={"source": "workbuddy"}).json()
    keys = {(m["provider_id"], m["model_id"]) for m in body["by_model"]}
    assert keys == {("auto", "glm-5.2"), ("auto", "glm-5.3"), ("glm-5.2", "glm-5.2")}
    source_id = client.get("/api/meta", params={"source": "workbuddy"}).json()["source_id"]
    assert source_id == "workbuddy"


def test_credit_zero_is_a_value_and_absent_is_none(client_factory, make_workbuddy):
    client = client_factory(
        workbuddy=[
            {
                "project_slug": "e--app-proj-a",
                "session_id": "s1",
                "records": [
                    # 混元免费行:credit 字段在值、值为 0
                    _record(
                        model="hy4-preview",
                        tier="hy4-preview",
                        prompt=500,
                        completion=100,
                        credit=0.0,
                        message_id="msg-hy",
                    ),
                    # 字段缺失:绝不被当成 0
                    _record(
                        model="kimi-k3-1",
                        tier="kimi-k3-1",
                        prompt=500,
                        completion=100,
                        message_id="msg-kimi",
                    ),
                ],
            }
        ]
    )
    body = client.get("/api/overview", params={"source": "workbuddy"}).json()
    credits = {m["model_id"]: m["credits"] for m in body["by_model"]}
    assert credits["hy4-preview"] == 0.0
    assert credits["kimi-k3-1"] is None
    assert all(m["credits_reported"] for m in body["by_model"])


def test_duplicate_message_id_billed_once(client_factory, make_workbuddy):
    records = [_record(prompt=100, completion=10, message_id="msg-dup", credit=1.0)]
    client = client_factory(
        workbuddy=[
            {"project_slug": "e--app-proj-a", "session_id": "s1", "records": records},
            # 同一 messageId 重放到另一个会话文件:仍只计一次
            {"project_slug": "e--app-proj-a", "session_id": "s2", "records": list(records)},
        ]
    )
    body = client.get("/api/overview", params={"source": "workbuddy"}).json()
    row = body["by_model"][0]
    assert row["request_count"] == 1
    assert row["total_tokens"] == 110
    assert row["credits"] == 1.0


def test_damaged_lines_and_payloadless_records_skipped(make_workbuddy, tmp_path):
    root = make_workbuddy(
        [
            {
                "project_slug": "e--app-proj-a",
                "session_id": "s1",
                "records": [_record(credit=1.0)],
            }
        ]
    )
    transcript = root / "projects" / "e--app-proj-a" / "s1.jsonl"
    lines = transcript.read_text(encoding="utf-8").splitlines()
    extra = [
        "{broken json",
        '{"type":"user","role":"user","message":{"role":"user","content":"hi"}}',
        # 无 rawUsage 载荷的 assistant 记录:无计费含义,不进任何合计
        '{"type":"message","role":"assistant","timestamp":1788000000000,"cwd":"E:/x",'
        '"providerData":{"model":"glm-5.2","requestModelId":"auto"}}',
    ]
    transcript.write_text("\n".join([*lines, *extra]), encoding="utf-8")
    client = TestClient(
        create_app(
            Settings(
                db_path=tmp_path / "z.sqlite",
                minimax_sessions_dir=tmp_path / "mm-missing",
                opencode_db_path=tmp_path / "oc-missing.db",
                workbuddy_dir=root,
                pricing_path=tmp_path / "pricing.json",
            )
        )
    )
    body = client.get("/api/overview", params={"source": "workbuddy"}).json()
    row = body["by_model"][0]
    assert row["request_count"] == 1
    assert row["total_tokens"] == 150


def test_double_write_db_is_never_metered(client_factory, make_workbuddy):
    # workbuddy.db 的 session_usage 复制了积分账(且故意写成不同数字):
    # 计量只认 jsonl 的 rawUsage,数据库连读都不该读。
    client = client_factory(
        workbuddy=[
            {
                "project_slug": "e--app-proj-a",
                "session_id": "s1",
                "records": [_record(credit=3.81)],
            }
        ],
        workbuddy_usage=[("s1", 32922, 168000, '{"4e54614b":999.0}')],
    )
    body = client.get("/api/overview", params={"source": "workbuddy"}).json()
    assert body["by_model"][0]["credits"] == 3.81
    projects = client.get("/api/projects", params={"source": "workbuddy"}).json()["projects"]
    assert projects[0]["directory"] == "E:/app/proj-a"
    assert projects[0]["credits"] == 3.81


def test_day_cut_and_window_filter(client_factory, make_workbuddy):
    client = client_factory(
        workbuddy=[
            {
                "project_slug": "e--app-proj-a",
                "session_id": "s1",
                "records": [
                    _record(ms=_MS_DAY1, prompt=100, credit=1.0, message_id="msg-d1"),
                    _record(ms=_MS_DAY2, prompt=300, credit=2.0, message_id="msg-d2"),
                ],
            }
        ]
    )
    day1 = ms_to_local_day(_MS_DAY1)
    trends = client.get("/api/trends/daily", params={"source": "workbuddy"}).json()
    by_day = {d["day"]: d for d in trends["days"]}
    assert len(by_day) == 2
    assert by_day[day1]["credits"] == 1.0
    windowed = client.get(
        "/api/trends/daily",
        params={"source": "workbuddy", "start": day1, "end": day1},
    ).json()
    assert [d["day"] for d in windowed["days"]] == [day1]
    assert windowed["days"][0]["total_tokens"] == 150


def test_meta_declares_traits_and_unpriced_credits(client_factory, make_workbuddy, tmp_path):
    import json

    root = make_workbuddy(
        [{"project_slug": "e--app-proj-a", "session_id": "s1", "records": [_record(credit=1.0)]}]
    )
    pricing = tmp_path / "pricing.json"
    pricing.write_text(
        json.dumps(
            {
                "version": 2,
                "models": {},
                "credit_prices": {"workbuddy|plan": {"cny_per_credit": 0.0495}},
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(
        create_app(
            Settings(
                db_path=tmp_path / "z.sqlite",
                minimax_sessions_dir=tmp_path / "mm-missing",
                opencode_db_path=tmp_path / "oc-missing.db",
                workbuddy_dir=root,
                pricing_path=pricing,
            )
        )
    )
    meta = client.get("/api/meta", params={"source": "workbuddy"}).json()
    assert meta["credit_reporting_sources"] == ["workbuddy"]
    assert "workbuddy" in meta["token_reporting_sources"]
    # 已录 plan 价 → 不再出现在 unpriced_credits
    assert meta["unpriced_credits"] == []
    overview = client.get("/api/overview", params={"source": "workbuddy"}).json()
    assert overview["credit_value_cny"]["plan"] == pytest.approx(0.0495, abs=1e-9)
    assert overview["credit_value_cny"]["pack"] is None


def test_source_missing_degrades_to_unavailable(client_factory):
    client = client_factory(rows=[{"model_id": "m1", "computed_total_tokens": 1}])
    meta = client.get("/api/meta").json()
    ref = next(s for s in meta["sources"] if s["id"] == "workbuddy")
    assert ref["available"] is False
    assert ref["error"]
    response = client.get("/api/overview", params={"source": "workbuddy"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"


def test_health_and_latency_degrade_to_zero_or_empty(client_factory, make_workbuddy):
    client = client_factory(
        workbuddy=[{"project_slug": "e--app-proj-a", "session_id": "s1", "records": [_record()]}]
    )
    health = client.get("/api/health", params={"source": "workbuddy"}).json()
    assert health["request_count"] == 1
    assert health["errored_requests"] == 0
    assert health["errors"] == []
    perf = client.get("/api/performance", params={"source": "workbuddy"}).json()
    assert perf["duration_ms"] is None
    assert perf["time_to_first_token_ms"] is None


@pytest.mark.live
def test_live_workbuddy_real_local_data():
    root = Path.home() / ".workbuddy"
    if not (root / "projects").is_dir():
        pytest.skip("no real ~/.workbuddy on this machine")
    source = WorkbuddySource(root)
    body = source.overview()
    assert body.request_count > 100
    assert body.total_tokens > 1_000_000
    assert body.credits is not None and body.credits > 100
    # 拆档恒等式逐行成立
    for m in body.by_model:
        assert (
            m.input_tokens + m.output_tokens + m.cache_creation_tokens + m.cache_read_tokens
            == m.total_tokens
        )
    assert ("auto", "glm-5.2") in {(m.provider_id, m.model_id) for m in body.by_model}

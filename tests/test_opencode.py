import pytest
from fastapi.testclient import TestClient

from zlens.api.app import create_app
from zlens.core.config import Settings
from zlens.sources.opencode import OpencodeSource

_MESSAGES = [
    {
        "id": "user-1",
        "session_id": "s1",
        "created": 1_700_000_000_000,
        "data": {"role": "user", "time": {"created": 1_700_000_000_000}},
    },
    {
        "id": "assistant-1",
        "session_id": "s1",
        "created": 1_700_000_000_100,
        "data": {
            "role": "assistant",
            "providerID": "opencode",
            "modelID": "x-preview-f-free",
            "tokens": {
                "total": 1_500,
                "input": 1_000,
                "output": 100,
                "reasoning": 50,
                "cache": {"read": 300, "write": 50},
            },
            "time": {"created": 1_700_000_000_100, "completed": 1_700_000_004_500},
        },
    },
]
_SESSIONS = [("s1", "p1", "E:/work/opencode", "Opencode demo")]


def test_opencode_adapter_maps_tokens_model_project_and_duration(make_opencode_db):
    source = OpencodeSource(make_opencode_db(_MESSAGES, _SESSIONS))

    overview = source.overview()
    row = overview.by_model[0]
    assert overview.request_count == 1
    assert overview.input_tokens == 1_000
    assert overview.output_tokens == 100
    assert overview.reasoning_tokens == 50
    assert overview.cache_creation_tokens == 50
    assert overview.cache_read_tokens == 300
    assert overview.total_tokens == 1_500
    assert (row.source, row.provider_id, row.model_id) == (
        "opencode",
        "opencode",
        "x-preview-f-free",
    )

    projects = source.usage_by_project_model()
    assert projects[0].directory == "E:/work/opencode"
    assert projects[0].title == "Opencode demo"

    durations, ttfts = source.latency_samples()
    assert durations == [4_400]
    assert ttfts == []


def test_opencode_adapter_skips_non_assistant_or_malformed_messages(make_opencode_db):
    messages = [
        {"id": "bad", "session_id": "s1", "data": "not-json"},
        {"id": "user", "session_id": "s1", "data": {"role": "user"}},
    ]
    source = OpencodeSource(make_opencode_db(messages, _SESSIONS))

    assert source.overview().request_count == 0
    assert source.model_ids() == []


def test_opencode_via_api(make_settings):
    client = TestClient(create_app(make_settings(opencode=_MESSAGES, opencode_sessions=_SESSIONS)))

    body = client.get("/api/overview", params={"source": "opencode"}).json()
    assert body["request_count"] == 1
    assert body["by_model"][0]["source"] == "opencode"
    assert (
        client.get("/api/performance", params={"source": "opencode"}).json()["duration_ms"][
            "p50_ms"
        ]
        == 4400.0
    )


@pytest.mark.live
def test_real_opencode_database_is_readable():
    settings = Settings()
    if not settings.opencode_db_path.exists():
        pytest.skip("real opencode database not present on this machine")

    source = OpencodeSource(settings.opencode_db_path)
    assert source.is_available()
    assert source.overview().request_count > 0

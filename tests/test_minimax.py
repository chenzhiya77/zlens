from zlens.sources.minimax import MinimaxSource

_EVENTS = [
    {"ms": 1_700_000_000_000, "input": 100, "output": 10, "cache_read": 1000, "total": 1110},
    {"ms": 1_700_000_100_000, "input": 200, "output": 20, "cache_write": 50, "total": 220},
]


def test_minimax_adapter_parses_ledger(make_minimax_sessions, tmp_path):
    root = make_minimax_sessions(
        [
            {
                "model": "MiniMax-M3",
                "workspace": "E:/work/minimax-proj",
                "events": _EVENTS,
            }
        ]
    )
    source = MinimaxSource(root)

    overview = source.overview()
    assert overview.request_count == 2
    assert overview.input_tokens == 300
    assert overview.output_tokens == 30
    assert overview.reasoning_tokens == 0  # upstream has no reasoning field
    assert overview.cache_creation_tokens == 50
    assert overview.cache_read_tokens == 1000
    assert overview.total_tokens == 1330

    row = overview.by_model[0]
    assert (row.source, row.provider_id, row.model_id) == ("minimax", "minimax", "MiniMax-M3")

    projects = source.usage_by_project_model()
    assert projects[0].directory == "E:/work/minimax-proj"
    assert projects[0].title == "minimax-proj"

    durations, ttfts = source.latency_samples()
    assert durations == [] and ttfts == []


def test_minimax_missing_directory_is_unavailable(tmp_path):
    from zlens.sources.base import SourceUnavailable

    source = MinimaxSource(tmp_path / "does-not-exist")
    try:
        source.is_available()
    except SourceUnavailable:
        pass
    else:
        raise AssertionError("missing MiniMax directory should raise SourceUnavailable")


def test_minimax_skips_damaged_lines(make_minimax_sessions, tmp_path):
    root = make_minimax_sessions([{"model": "M1", "workspace": "E:/p", "events": _EVENTS[:1]}])
    ledger = next(root.glob("*/*/*/*/ledger.jsonl"))
    ledger.write_text(ledger.read_text(encoding="utf-8") + "\n{not valid json\n", encoding="utf-8")

    source = MinimaxSource(root)
    assert source.overview().request_count == 1


def test_minimax_via_api(client_factory):
    client = client_factory(
        minimax=[{"model": "MiniMax-M3", "workspace": "E:/work/mx", "events": _EVENTS}]
    )

    body = client.get("/api/overview").json()
    assert body["request_count"] == 2
    assert body["by_model"][0]["source"] == "minimax"
    assert body["by_model"][0]["model_id"] == "MiniMax-M3"

    meta = client.get("/api/meta").json()
    assert meta["source_id"] == "zcode+minimax"
    assert meta["request_count"] == 2

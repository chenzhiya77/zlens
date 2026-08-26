def test_overview_totals_and_by_model_ranking(client_factory):
    rows = [
        ("anthropic", "claude-a", 1, 100, 10, 5, 20, 1000, 1135),
        ("anthropic", "claude-a", 2, 50, 5, 0, 0, 500, 555),
        ("openai", "gpt-b", 3, 10, 2, 1, 0, 0, 13),
    ]
    body = client_factory(rows).get("/api/overview").json()

    assert body["request_count"] == 3
    assert body["input_tokens"] == 160
    assert body["output_tokens"] == 17
    assert body["reasoning_tokens"] == 6
    assert body["cache_creation_tokens"] == 20
    assert body["cache_read_tokens"] == 1500
    assert body["total_tokens"] == 1703

    assert [m["model_id"] for m in body["by_model"]] == ["claude-a", "gpt-b"]
    top = body["by_model"][0]
    assert top["provider_id"] == "anthropic"
    assert top["request_count"] == 2
    assert top["input_tokens"] == 150
    assert top["cache_read_tokens"] == 1500
    assert top["total_tokens"] == 1690


def test_overview_on_empty_database(client_factory):
    body = client_factory([]).get("/api/overview").json()

    assert body["request_count"] == 0
    assert body["total_tokens"] == 0
    assert body["by_model"] == []


def test_overview_maps_missing_identity_to_unknown(client_factory):
    rows = [(None, None, 1, 1, 1, 0, 0, 0, 2)]
    body = client_factory(rows).get("/api/overview").json()

    assert body["by_model"][0]["provider_id"] == "unknown"
    assert body["by_model"][0]["model_id"] == "unknown"
    assert body["total_tokens"] == 2

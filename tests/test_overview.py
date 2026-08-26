def test_overview_totals_and_by_model_ranking(client_factory):
    rows = [
        {
            "provider_id": "anthropic",
            "model_id": "claude-a",
            "input_tokens": 100,
            "output_tokens": 10,
            "reasoning_tokens": 5,
            "cache_creation_input_tokens": 20,
            "cache_read_input_tokens": 1000,
            "computed_total_tokens": 1135,
        },
        {
            "provider_id": "anthropic",
            "model_id": "claude-a",
            "input_tokens": 50,
            "output_tokens": 5,
            "cache_read_input_tokens": 500,
            "computed_total_tokens": 555,
        },
        {
            "provider_id": "openai",
            "model_id": "gpt-b",
            "input_tokens": 10,
            "output_tokens": 2,
            "reasoning_tokens": 1,
            "computed_total_tokens": 13,
        },
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
    rows = [{"provider_id": None, "model_id": None, "computed_total_tokens": 2}]
    body = client_factory(rows).get("/api/overview").json()

    assert body["by_model"][0]["provider_id"] == "unknown"
    assert body["by_model"][0]["model_id"] == "unknown"
    assert body["total_tokens"] == 2

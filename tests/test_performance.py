from zlens.core.stats import latency_stats, percentile


def test_percentile_linear_interpolation():
    samples = [100, 200, 300, 400]

    assert percentile(samples, 50) == 250  # rank 1.5 -> midpoint
    assert percentile(samples, 90) == 370  # rank 2.7
    assert percentile(samples, 99) == 397  # rank 2.97
    assert percentile([42], 99) == 42


def test_latency_stats_reports_sample_count_and_none_for_empty():
    stats = latency_stats([100, 200, 300, 400])

    assert stats.sample_count == 4
    assert (stats.p50_ms, stats.p90_ms, stats.p99_ms) == (250.0, 370.0, 397.0)
    assert latency_stats([]) is None


def test_performance_endpoint_separates_ttft_nulls(client_factory):
    body = (
        client_factory(
            rows=[
                {"duration_ms": 100, "time_to_first_token_ms": 50},
                {"duration_ms": 200},
                {"duration_ms": 300, "time_to_first_token_ms": 150},
                {"duration_ms": 400},
            ]
        )
        .get("/api/performance")
        .json()
    )

    assert body["duration_ms"]["sample_count"] == 4
    assert body["duration_ms"]["p50_ms"] == 250.0
    assert body["time_to_first_token_ms"]["sample_count"] == 2
    assert body["time_to_first_token_ms"]["p50_ms"] == 100.0


def test_performance_endpoint_on_empty_database(client_factory):
    body = client_factory([]).get("/api/performance").json()

    assert body == {"duration_ms": None, "time_to_first_token_ms": None}

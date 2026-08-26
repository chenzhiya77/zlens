def test_health_counts_retries_errors_cancels_and_context(client_factory):
    body = (
        client_factory(
            rows=[
                {"retry_count": 2, "error_type": "rate_limit", "error_code": "429"},
                {"cancelled_by_user": 1},
                {"context_exceeded": 1, "error_type": "context_length"},
                {},
            ]
        )
        .get("/api/health")
        .json()
    )

    assert body["request_count"] == 4
    assert body["requests_with_retries"] == 1
    assert body["total_retries"] == 2
    assert body["cancelled_by_user"] == 1
    assert body["context_exceeded"] == 1
    assert body["errored_requests"] == 2
    assert body["errors"] == [
        # Counts tie at 1; ties break by error_type ascending for stable output.
        {"source": "zcode", "error_type": "context_length", "error_code": None, "request_count": 1},
        {"source": "zcode", "error_type": "rate_limit", "error_code": "429", "request_count": 1},
    ]


def test_health_on_clean_database(client_factory):
    body = client_factory(rows=[{}, {}]).get("/api/health").json()

    assert body["request_count"] == 2
    assert body["errored_requests"] == 0
    assert body["errors"] == []

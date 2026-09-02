"""The instant window [since, until) on /api/performance and /api/health (T27).

Half-open on purpose: a request exactly at `since` counts, one exactly at
`until` does not — a date-level custom range then maps to [day 00:00,
day+1 00:00) without fabricating an end-of-day bound. Every adapter windows its
own sampling (T15 pushdown discipline): zcode in SQL, minimax/opencode over
loaded records.
"""

from datetime import datetime

# Whole seconds only, so the ISO since/until strings the API parses map back to
# exact epoch-ms bounds (int(ts * 1000) round-trips losslessly).
_T_BEFORE = 1_700_000_000_000
_T_IN = 1_700_000_700_000
_T_SINCE = 1_700_000_600_000  # exactly at since -> included
_T_UNTIL = 1_700_000_900_000  # exactly at until -> excluded

_SINCE = datetime.fromtimestamp(_T_SINCE / 1000).isoformat()
_UNTIL = datetime.fromtimestamp(_T_UNTIL / 1000).isoformat()


def _zcode_rows():
    return [
        {
            "provider_id": "chan-a",
            "model_id": "m",
            "started_at": started,
            "duration_ms": duration,
            "time_to_first_token_ms": ttft,
            "retry_count": retries,
            "error_type": error,
        }
        for started, duration, ttft, retries, error in [
            (_T_BEFORE, 1_000, None, 0, None),
            (_T_IN, 2_000, 500, 2, "server_error"),
            (_T_SINCE, 3_000, 700, 0, None),
            (_T_UNTIL, 4_000, None, 0, None),
        ]
    ]


def test_health_windows_half_open_instant_range(client_factory):
    client = client_factory(rows=_zcode_rows())

    body = client.get(f"/api/health?since={_SINCE}&until={_UNTIL}").json()

    # In-window: _T_IN plus the since-edge row; the until-edge row is out.
    assert body["request_count"] == 2
    assert body["total_retries"] == 2
    assert body["errored_requests"] == 1
    assert [(e["error_type"], e["request_count"]) for e in body["errors"]] == [("server_error", 1)]


def test_performance_windows_half_open_instant_range(client_factory):
    client = client_factory(rows=_zcode_rows())

    body = client.get(f"/api/performance?since={_SINCE}&until={_UNTIL}").json()

    # Durations inside: 2_000 (_T_IN) and 3_000 (since edge); 1_000/4_000 are out.
    assert body["duration_ms"]["sample_count"] == 2
    # Inclusive linear interpolation: p99 of [2000, 3000] = 2000*0.01 + 3000*0.99.
    assert body["duration_ms"]["p99_ms"] == 2_990.0
    # TTFTs inside: 500 (_T_IN) and 700 (since edge) — two samples, not one.
    assert body["time_to_first_token_ms"]["sample_count"] == 2
    assert body["time_to_first_token_ms"]["p99_ms"] == 698.0


def test_no_window_stays_unbounded(client_factory):
    client = client_factory(rows=_zcode_rows())

    assert client.get("/api/health").json()["request_count"] == 4


def test_inverted_or_equal_or_malformed_window_is_422(client_factory):
    client = client_factory(rows=_zcode_rows())

    assert client.get(f"/api/health?since={_UNTIL}&until={_SINCE}").status_code == 422
    assert client.get(f"/api/health?since={_SINCE}&until={_SINCE}").status_code == 422
    assert client.get("/api/health?since=not-a-time").status_code == 422


def test_minimax_windows_request_count(client_factory):
    client = client_factory(
        minimax=[
            {"events": [{"ms": _T_BEFORE, "input": 10, "output": 5, "total": 15}]},
            {"events": [{"ms": _T_IN, "input": 10, "output": 5, "total": 15}]},
        ],
    )

    body = client.get(f"/api/health?source=minimax&since={_SINCE}&until={_UNTIL}").json()

    assert body["request_count"] == 1
    assert client.get("/api/health?source=minimax").json()["request_count"] == 2


def test_opencode_windows_health_and_latency(client_factory):
    messages = [
        {
            "id": f"a-{started}",
            "session_id": "s1",
            "created": started,
            "data": {
                "role": "assistant",
                "providerID": "opencode",
                "modelID": "m",
                "tokens": {
                    "total": 100,
                    "input": 60,
                    "output": 30,
                    "reasoning": 10,
                    "cache": {"read": 0, "write": 0},
                },
                "time": {"created": started, "completed": started + 4_000},
            },
        }
        for started in (_T_BEFORE, _T_IN, _T_SINCE, _T_UNTIL)
    ]
    client = client_factory(opencode=messages, opencode_sessions=[("s1", "p1", "E:/work/oc", "T")])

    body = client.get(f"/api/health?source=opencode&since={_SINCE}&until={_UNTIL}").json()
    assert body["request_count"] == 2

    perf = client.get(f"/api/performance?source=opencode&since={_SINCE}&until={_UNTIL}").json()
    assert perf["duration_ms"]["sample_count"] == 2
    assert perf["duration_ms"]["p99_ms"] == 4_000.0

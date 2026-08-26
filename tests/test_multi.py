def test_multi_source_merges_totals_and_tags_rows(client_factory):
    client = client_factory(
        rows=[{"model_id": "z1", "computed_total_tokens": 1000}],
        minimax=[
            {
                "model": "MiniMax-M3",
                "workspace": "E:/work/mx",
                "events": [{"ms": 1_700_000_000_000, "input": 5, "output": 5, "total": 500}],
            }
        ],
    )

    body = client.get("/api/overview").json()

    assert body["request_count"] == 2
    assert body["total_tokens"] == 1500
    assert {m["source"] for m in body["by_model"]} == {"zcode", "minimax"}

    meta = client.get("/api/meta").json()
    assert meta["source_id"] == "zcode+minimax"


def test_source_filter_selects_one_adapter(client_factory):
    client = client_factory(
        rows=[{"model_id": "z1", "computed_total_tokens": 1000}],
        minimax=[
            {
                "model": "MiniMax-M3",
                "workspace": "E:/work/mx",
                "events": [{"ms": 1_700_000_000_000, "input": 5, "output": 5, "total": 500}],
            }
        ],
    )

    minimax = client.get("/api/overview", params={"source": "minimax"}).json()
    assert minimax["request_count"] == 1
    assert minimax["total_tokens"] == 500
    assert minimax["by_model"][0]["model_id"] == "MiniMax-M3"

    zcode = client.get("/api/overview", params={"source": "zcode"}).json()
    assert zcode["total_tokens"] == 1000


def test_unknown_source_filter_reports_unavailable(client_factory):
    client = client_factory(rows=[{"model_id": "z1", "computed_total_tokens": 1}])

    response = client.get("/api/overview", params={"source": "nope"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"


def test_broken_zcode_does_not_sink_other_sources(client_factory, tmp_path):
    import sqlite3

    broken = tmp_path / "broken.sqlite"
    con = sqlite3.connect(broken)
    con.execute("CREATE TABLE model_usage (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()

    from fastapi.testclient import TestClient

    from zlens.api.app import create_app
    from zlens.core.config import Settings

    make_minimax_root = tmp_path / "minimax" / "v2" / "sessions"
    client = client_factory(
        minimax=[
            {
                "model": "MiniMax-M3",
                "workspace": "E:/work/mx",
                "events": [{"ms": 1_700_000_000_000, "input": 1, "output": 1, "total": 10}],
            }
        ]
    )
    # swap in the broken zcode db on top of the working minimax fixture
    client = TestClient(
        create_app(
            Settings(
                db_path=broken,
                minimax_sessions_dir=make_minimax_root,
                opencode_db_path=tmp_path / "opencode-missing.db",
            )
        )
    )

    response = client.get("/api/overview")
    assert response.status_code == 200
    assert response.json()["by_model"][0]["source"] == "minimax"

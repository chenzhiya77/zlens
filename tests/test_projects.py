def test_projects_fold_join_and_cost_rule(client_factory, tmp_path):
    client = client_factory(
        rows=[
            {
                "model_id": "a",
                "session_id": "s1",
                "input_tokens": 1_000_000,
                "computed_total_tokens": 100,
            },
            {"model_id": "b", "session_id": "s2", "computed_total_tokens": 500},
            {
                "model_id": "a",
                "session_id": "missing",
                "input_tokens": 500_000,
                "computed_total_tokens": 50,
            },
            {
                "model_id": "a",
                "session_id": "s3",
                "input_tokens": 250_000,
                "computed_total_tokens": 10,
            },
        ],
        sessions=[
            ("s1", "E:/work/proj", "T1"),
            ("s2", "E:/work/proj", "T2"),
            ("s3", "", ""),
        ],
    )
    _write_pricing(tmp_path)
    # Rebind pricing: client_factory pins the default (missing) pricing path.
    from zlens.core.cost import PriceTable, fold_projects

    report = fold_projects(
        client.app.state.source.usage_by_project_model(), PriceTable.load(_write_pricing(tmp_path))
    )
    projects = {p.directory: p for p in report.projects}

    assert set(projects) == {"E:/work/proj", "(unknown)"}
    proj = projects["E:/work/proj"]
    assert (proj.request_count, proj.total_tokens) == (2, 600)
    assert proj.title == "T2"  # representative title = MAX(title) of the project's sessions
    assert proj.estimated_cost is None  # unpriced model b contributes -> honest null

    orphan = projects["(unknown)"]
    assert (orphan.request_count, orphan.total_tokens) == (2, 60)
    assert orphan.estimated_cost == 0.75  # (1e6 + 5e5 + 2.5e5) * 1.0 / 1e6


def test_projects_via_api_ordering(client_factory):
    body = (
        client_factory(
            rows=[
                {"model_id": "a", "session_id": "s1", "computed_total_tokens": 900},
                {"model_id": "a", "session_id": "s2", "computed_total_tokens": 100},
            ],
            sessions=[("s1", "E:/big", "Big"), ("s2", "E:/small", "Small")],
        )
        .get("/api/projects")
        .json()
    )

    assert [p["directory"] for p in body["projects"]] == ["E:/big", "E:/small"]


def _write_pricing(tmp_path):
    import json

    path = tmp_path / "pricing.json"
    path.write_text(
        json.dumps({"version": 1, "models": {"zcode|unknown|a": {"input": 1.0, "output": 0.0}}}),
        encoding="utf-8",
    )
    return path

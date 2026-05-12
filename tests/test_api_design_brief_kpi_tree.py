from tests._design_brief_artifact_endpoint_helpers import api_client, seed_design_brief


def test_design_brief_kpi_tree_api(tmp_path) -> None:
    db_path = str(tmp_path / "kpi_tree.db")
    brief_id = seed_design_brief(db_path, label="KPI Tree")
    client = api_client(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/kpi-tree")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "max.design_brief.kpi_tree.v1"
    assert payload["brief_id"] == brief_id
    assert payload["title"] == "KPI Tree API Brief"
    assert payload["north_star_metric"]["id"] == "NS1"
    assert payload["outcome_metrics"]
    assert payload["input_metrics"]
    assert payload["guardrail_metrics"]
    assert payload["measurement_plan"]["instrumentation_events"]


def test_design_brief_kpi_tree_markdown_outputs_match(tmp_path) -> None:
    db_path = str(tmp_path / "kpi_tree_markdown.db")
    brief_id = seed_design_brief(db_path, label="KPI Tree")
    client = api_client(db_path)

    alias_response = client.get(f"/api/v1/design-briefs/{brief_id}/kpi-tree.md")
    format_response = client.get(f"/api/v1/design-briefs/{brief_id}/kpi-tree?format=markdown")

    assert alias_response.status_code == 200
    assert alias_response.headers["content-type"].startswith("text/markdown")
    assert "attachment; filename=" in alias_response.headers["content-disposition"]
    assert alias_response.text.startswith("# KPI Tree: KPI Tree API Brief")
    assert format_response.status_code == 200
    assert format_response.text == alias_response.text


def test_design_brief_kpi_tree_missing_and_unsupported_format(tmp_path) -> None:
    db_path = str(tmp_path / "kpi_tree_missing.db")
    brief_id = seed_design_brief(db_path, label="KPI Tree")
    client = api_client(db_path)

    missing = client.get("/api/v1/design-briefs/dbf-missing/kpi-tree")
    unsupported = client.get(f"/api/v1/design-briefs/{brief_id}/kpi-tree?format=csv")

    assert missing.status_code == 404
    assert missing.json()["detail"] == "Design brief not found: dbf-missing"
    assert unsupported.status_code == 422

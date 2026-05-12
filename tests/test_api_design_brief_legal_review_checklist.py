from max.analysis.design_brief_legal_review_checklist import CSV_COLUMNS, SCHEMA_VERSION

from tests._design_brief_artifact_endpoint_helpers import api_client, seed_design_brief


def test_design_brief_legal_review_checklist_api(tmp_path) -> None:
    db_path = str(tmp_path / "legal_review_checklist.db")
    brief_id = seed_design_brief(db_path, label="Legal Review Checklist")
    client = api_client(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/legal-review-checklist")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["brief_id"] == brief_id
    assert payload["summary"]["review_gate"] == "ready_for_legal_review"
    assert payload["sections"]
    assert payload["checklist_items"]
    assert payload["unresolved_legal_questions"] == []
    assert payload["evidence_references"]

    markdown_response = client.get(
        f"/api/v1/design-briefs/{brief_id}/legal-review-checklist.md"
    )
    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/markdown")
    assert "attachment; filename=" in markdown_response.headers["content-disposition"]
    assert markdown_response.text.startswith("# Legal Review Checklist:")

    csv_response = client.get(
        f"/api/v1/design-briefs/{brief_id}/legal-review-checklist?format=csv"
    )
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in csv_response.headers["content-disposition"]
    assert csv_response.text.splitlines()[0] == ",".join(CSV_COLUMNS)

    alias_csv_response = client.get(
        f"/api/v1/design-briefs/{brief_id}/legal-review-checklist.csv"
    )
    assert alias_csv_response.status_code == 200
    assert alias_csv_response.headers["content-type"].startswith("text/csv")

    unsupported = client.get(
        f"/api/v1/design-briefs/{brief_id}/legal-review-checklist?format=yaml"
    )
    assert unsupported.status_code == 400
    assert unsupported.json()["detail"] == "Unsupported legal review checklist format: yaml"

    missing = client.get("/api/v1/design-briefs/dbf-missing/legal-review-checklist")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Design brief not found: dbf-missing"

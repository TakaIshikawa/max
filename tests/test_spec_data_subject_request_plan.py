from __future__ import annotations

import csv
import io

from max.spec.data_subject_request_plan import DATA_SUBJECT_REQUEST_PLAN_SCHEMA_VERSION, KIND, generate_data_subject_request_plan, render_data_subject_request_plan_csv, render_data_subject_request_plan_markdown


def _spec() -> dict:
    return {"schema_version": "tact-spec-preview/v1", "kind": "tact.project_spec", "source": {"idea_id": "dsr-1", "domain": "privacy"}, "project": {"title": "Customer Privacy Portal", "workflow_context": "customer account export", "specific_user": "privacy operator"}, "solution": {"technical_approach": "FastAPI stores customer email, payment notes, and export records."}, "execution": {"risks": ["Deletion exceptions need legal review."]}, "evidence": {"sig-1": "Customer asked for export proof."}}


def test_data_subject_request_plan_sections_markdown_and_csv() -> None:
    plan = generate_data_subject_request_plan(_spec())
    assert plan["schema_version"] == DATA_SUBJECT_REQUEST_PLAN_SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["source"]["idea_id"] == "dsr-1"
    assert plan["summary"]["title"] == "Customer Privacy Portal"
    assert plan["request_intake"]
    assert plan["identity_verification"]
    assert plan["data_discovery"]
    assert plan["fulfillment"]
    assert plan["exception_handling"]
    assert plan["audit_evidence"]
    assert any("Privacy-sensitive" in note for note in plan["risk_notes"])
    assert "# Customer Privacy Portal Data Subject Request Plan" in render_data_subject_request_plan_markdown(plan)
    rows = list(csv.DictReader(io.StringIO(render_data_subject_request_plan_csv(plan))))
    assert [row["section"] for row in rows][:2] == ["request_intake", "identity_verification"]

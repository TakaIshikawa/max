from __future__ import annotations

import csv
import io

from max.spec.audit_logging_plan import AUDIT_LOGGING_PLAN_SCHEMA_VERSION, KIND, generate_audit_logging_plan, render_audit_logging_plan_csv, render_audit_logging_plan_markdown


def test_audit_logging_plan_escalates_sensitive_coverage() -> None:
    plan = generate_audit_logging_plan({"schema_version": "tact-spec-preview/v1", "kind": "tact.project_spec", "source": {"idea_id": "audit-1"}, "project": {"title": "Payment Admin Export", "workflow_context": "admin data export"}, "solution": {"technical_approach": "Includes payment, privacy, security and compliance audit events."}, "evidence": {"sig-1": "Need audit proof"}})
    assert plan["schema_version"] == AUDIT_LOGGING_PLAN_SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["summary"]["coverage_recommendation"] == "elevated"
    assert any(item["name"] == "sensitive_data_accessed" for item in plan["auditable_events"])
    assert plan["log_sinks"]
    assert plan["retention"]
    assert plan["alerting"]
    assert "elevated audit coverage" in plan["recommendations"][0]
    assert "# Payment Admin Export Audit Logging Plan" in render_audit_logging_plan_markdown(plan)
    assert list(csv.DictReader(io.StringIO(render_audit_logging_plan_csv(plan))))[0]["section"] == "auditable_events"

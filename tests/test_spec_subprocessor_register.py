from __future__ import annotations

import csv
import io

from max.spec.subprocessor_register import KIND, SUBPROCESSOR_REGISTER_SCHEMA_VERSION, generate_subprocessor_register, render_subprocessor_register_csv, render_subprocessor_register_markdown


def test_subprocessor_register_infers_vendors_and_contract_actions() -> None:
    spec = {"schema_version": "tact-spec-preview/v1", "kind": "tact.project_spec", "source": {"idea_id": "sub-1"}, "project": {"title": "Customer Workflow", "workflow_context": "customer email escalation"}, "solution": {"suggested_stack": {"ai": "OpenAI", "messaging": "Slack", "payments": "Stripe", "database": "Postgres"}, "technical_approach": "Send customer email and payment notes to Slack and OpenAI."}}
    register = generate_subprocessor_register(spec)
    vendors = {row["vendor_id"] for row in register["subprocessors"]}
    assert register["schema_version"] == SUBPROCESSOR_REGISTER_SCHEMA_VERSION
    assert register["kind"] == KIND
    assert {"openai", "slack", "stripe", "postgres"} <= vendors
    assert register["summary"]["high_risk_count"] >= 3
    assert "Confirm contract status" in register["recommendations"][0]
    assert "# Customer Workflow Subprocessor Register" in render_subprocessor_register_markdown(register)
    rows = list(csv.DictReader(io.StringIO(render_subprocessor_register_csv(register))))
    assert rows[0]["contract_status"] == "needs_review"

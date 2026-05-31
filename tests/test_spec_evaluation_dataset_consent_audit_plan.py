from __future__ import annotations

from max.spec.evaluation_dataset_consent_audit_plan import generate_evaluation_dataset_consent_audit_plan


def test_consent_audit_groups_status_and_flags_revoked() -> None:
    plan = generate_evaluation_dataset_consent_audit_plan({"metadata": {"evaluation_dataset_consent_audit": {"datasets": [{"dataset": "gold", "consent_status": "valid", "provenance": "crm"}, {"dataset": "holdout", "consent_status": "revoked", "provenance": "crm"}]}}})
    assert plan["audit_scope"][0]["name"] == "holdout"
    assert {group["name"] for group in plan["consent_status_groups"]} == {"revoked", "valid"}
    assert "Remove revoked records" in plan["remediation_actions"][0]["description"]


def test_consent_audit_blocks_missing_provenance() -> None:
    plan = generate_evaluation_dataset_consent_audit_plan({"metadata": {"evaluation_dataset_consent_audit": {"dataset_entries": [{"name": "eval", "consent": "valid"}]}}})
    assert "Block dataset use" in plan["remediation_actions"][0]["description"]


def test_consent_audit_empty_input_bootstraps_checklist() -> None:
    plan = generate_evaluation_dataset_consent_audit_plan({})
    assert plan["audit_scope"]
    assert plan["completion_criteria"]

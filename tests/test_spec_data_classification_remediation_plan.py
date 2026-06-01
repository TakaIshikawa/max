from __future__ import annotations

import pytest

from max.spec.data_classification_remediation_plan import generate_data_classification_remediation_plan


def test_data_classification_remediation_plan_prioritizes_by_severity_and_systems() -> None:
    plan = generate_data_classification_remediation_plan(_spec())

    assert [item["name"] for item in plan["remediation_priorities"]] == ["payments table", "support export", "marketing field"]
    assert plan["remediation_priorities"][0]["severity"] == "high"
    assert set(plan) >= {"access_control_updates", "retention_follow_up", "audit_evidence_follow_up"}


def test_data_classification_remediation_plan_flags_missing_owners() -> None:
    plan = generate_data_classification_remediation_plan(_spec())

    assert [item["name"] for item in plan["escalations"]] == ["support export"]
    assert plan["escalations"][0]["status"] == "owner_missing"


def test_data_classification_remediation_plan_is_deterministic() -> None:
    assert generate_data_classification_remediation_plan(_spec()) == generate_data_classification_remediation_plan(_spec())


def test_data_classification_remediation_plan_requires_items() -> None:
    with pytest.raises(ValueError, match="misclassified items"):
        generate_data_classification_remediation_plan({"metadata": {"data_classification_remediation": {}}})


def _spec() -> dict:
    return {
        "metadata": {
            "data_classification_remediation": {
                "misclassifications": [
                    {"name": "marketing field", "severity": "medium", "owner": "data steward", "affected_systems": ["crm"], "current_classification": "public", "target_classification": "internal"},
                    {"name": "support export", "severity": "high", "affected_systems": ["zendesk"], "retention_implications": "shorten retention"},
                    {"name": "payments table", "severity": "high", "owner": "payments", "affected_systems": ["warehouse", "billing"], "current_classification": "internal", "target_classification": "restricted"},
                ]
            }
        }
    }

from __future__ import annotations

import pytest

from max.spec.audit_log_coverage_remediation_plan import generate_audit_log_coverage_remediation_plan


def test_audit_log_coverage_remediation_plan_groups_by_system_and_event() -> None:
    plan = generate_audit_log_coverage_remediation_plan(_spec())

    assert [item["name"] for item in plan["coverage_gaps_by_system"]] == [
        "admin - permission_change",
        "api - auth_failure",
        "api - data_export",
    ]
    assert set(plan) >= {"critical_actions", "owner_follow_up", "validation_evidence"}


def test_audit_log_coverage_remediation_plan_flags_blockers() -> None:
    plan = generate_audit_log_coverage_remediation_plan(_spec())

    assert [item["name"] for item in plan["critical_actions"]] == [
        "admin - permission_change",
        "api - auth_failure",
        "api - data_export",
    ]


def test_audit_log_coverage_remediation_plan_is_deterministic() -> None:
    assert generate_audit_log_coverage_remediation_plan(_spec()) == generate_audit_log_coverage_remediation_plan(_spec())


def test_audit_log_coverage_remediation_plan_requires_gaps() -> None:
    with pytest.raises(ValueError, match="coverage gaps"):
        generate_audit_log_coverage_remediation_plan({"metadata": {"audit_log_coverage_remediation": {}}})


def _spec() -> dict:
    return {
        "metadata": {
            "audit_log_coverage_remediation": {
                "coverage_gaps": [
                    {"system": "api", "event_category": "data_export", "severity": "critical", "owner": "platform", "missing_fields": ["actor"], "retention_period": "90 days", "required_retention": "365 days", "validation_evidence": "query sample"},
                    {"system": "admin", "event_category": "permission_change", "owner": "", "retention_period": "365 days", "required_retention": "365 days"},
                    {"system": "api", "event_category": "auth_failure", "owner": "security", "retention_period": "30 days", "required_retention": "365 days"},
                ]
            }
        }
    }

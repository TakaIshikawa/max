from __future__ import annotations

from max.spec.data_subject_access_request_verification_plan import (
    generate_data_subject_access_request_verification_plan,
)


def test_dsar_verification_plan_contains_required_sections_and_ordering() -> None:
    plan = generate_data_subject_access_request_verification_plan(
        {
            "metadata": {
                "data_subject_access_request_verification": {
                    "requests": [
                        {"name": "case-b", "owner": "privacy_ops", "severity": "low", "subject": "subject-b"},
                        {"name": "case-a", "owner": "legal_ops", "severity": "critical", "subject": "subject-a", "due": "2026-06-01"},
                    ]
                }
            }
        }
    )

    assert "# Data Subject Access Request Verification Plan" in plan
    assert "## Identity Verification" in plan
    assert "## Data Inventory Lookup" in plan
    assert "## Response Packaging" in plan
    assert "## Exception Handling" in plan
    assert "## Audit Evidence" in plan
    assert "## Completion Signoff" in plan
    assert plan.index("case-a") < plan.index("case-b")
    assert "| case-a | legal_ops | critical | subject-a | 2026-06-01 |" in plan


def test_dsar_verification_plan_handles_missing_optional_fields() -> None:
    plan = generate_data_subject_access_request_verification_plan({"requests": [{"request_id": "case-1"}]})

    assert "| case-1 | privacy_owner | medium | unspecified subject | not scheduled |" in plan


def test_dsar_verification_plan_is_deterministic() -> None:
    payload = {"requests": [{"name": "z"}, {"name": "a"}]}

    assert generate_data_subject_access_request_verification_plan(payload) == generate_data_subject_access_request_verification_plan(payload)

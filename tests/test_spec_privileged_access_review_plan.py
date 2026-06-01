from __future__ import annotations

import pytest

from max.spec.privileged_access_review_plan import generate_privileged_access_review_plan


def test_privileged_access_review_plan_contains_expected_sections() -> None:
    plan = generate_privileged_access_review_plan(_spec("2026-Q3"))

    assert plan["summary"]["system_name"] == "payments admin"
    assert [item["name"] for item in plan["role_attestations"]] == ["break glass", "super admin"]
    assert set(plan) >= {"evidence_collection", "exception_handling", "revocation_tasks", "completion_criteria"}


def test_privileged_access_review_plan_flags_overdue_review_windows() -> None:
    plan = generate_privileged_access_review_plan(_spec("overdue 2026-Q1"))

    assert plan["summary"]["overdue"] is True
    assert {item["status"] for item in plan["role_attestations"]} == {"overdue"}


@pytest.mark.parametrize("field,match", [("system_name", "system name"), ("privileged_roles", "privileged roles"), ("reviewers", "reviewers"), ("review_window", "review window")])
def test_privileged_access_review_plan_validates_required_inputs(field: str, match: str) -> None:
    hints = dict(_spec("2026-Q3")["metadata"]["privileged_access_review"])
    hints[field] = [] if field == "privileged_roles" else ""

    with pytest.raises(ValueError, match=match):
        generate_privileged_access_review_plan({"metadata": {"privileged_access_review": hints}})


def test_privileged_access_review_plan_is_deterministic() -> None:
    assert generate_privileged_access_review_plan(_spec("2026-Q3")) == generate_privileged_access_review_plan(_spec("2026-Q3"))


def _spec(window: str) -> dict:
    return {
        "metadata": {
            "privileged_access_review": {
                "system_name": "payments admin",
                "privileged_roles": ["super admin", "break glass"],
                "reviewers": ["iam reviewer", "security lead"],
                "review_window": window,
                "evidence_sources": ["IAM export"],
                "exception_policy": "exceptions require CISO approval",
                "revocation_owners": ["iam operator"],
            }
        }
    }

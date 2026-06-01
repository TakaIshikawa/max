from __future__ import annotations

import pytest

from max.spec.subprocessor_change_notification_plan import generate_subprocessor_change_notification_plan


def test_subprocessor_change_notification_plan_identifies_notice_requirements() -> None:
    plan = generate_subprocessor_change_notification_plan(_spec())

    assert [item["name"] for item in plan["change_inventory"]] == ["Beta LLM", "Old Email"]
    assert plan["change_inventory"][0]["regions"] == "EU, US"
    assert plan["change_inventory"][0]["data_categories"] == "support tickets"
    assert set(plan) >= {"customer_notice_requirements", "legal_review", "objection_handling", "rollout_gates"}


def test_subprocessor_change_notification_plan_escalates_short_notice_windows() -> None:
    plan = generate_subprocessor_change_notification_plan(_spec())

    assert [item["name"] for item in plan["escalation_actions"]] == ["Beta LLM"]
    assert plan["escalation_actions"][0]["status"] == "escalated"


def test_subprocessor_change_notification_plan_is_deterministic() -> None:
    assert generate_subprocessor_change_notification_plan(_spec()) == generate_subprocessor_change_notification_plan(_spec())


def test_subprocessor_change_notification_plan_requires_subprocessors() -> None:
    with pytest.raises(ValueError, match="subprocessors"):
        generate_subprocessor_change_notification_plan({"metadata": {"subprocessor_change_notification": {}}})


def _spec() -> dict:
    return {
        "metadata": {
            "subprocessor_change_notification": {
                "subprocessors": [
                    {"name": "Old Email", "change_type": "removed", "products": ["notifications"], "regions": ["US"], "data_categories": ["email"], "notice_window": "30 days"},
                    {"name": "Beta LLM", "change_type": "added", "products": ["support"], "regions": ["EU", "US"], "data_categories": ["support tickets"], "notice_window": "7 days short"},
                ]
            }
        }
    }

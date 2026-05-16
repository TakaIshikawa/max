from __future__ import annotations

from max.spec.access_review_plan import generate_access_review_plan


def test_access_review_plan_covers_access_review_sections() -> None:
    plan = generate_access_review_plan(
        {
            "project": {"title": "Admin Console"},
            "access": {
                "systems": ["prod-db", "admin-api"],
                "privileged_roles": ["ReadOnly", "Owner", {"name": "Support Admin"}],
                "data_sensitivity": "confidential PII",
                "approvers": ["security", "engineering"],
            },
            "evidence": {"insight_ids": ["iam-1"]},
        }
    )

    assert plan["kind"] == "max.access_review_plan"
    assert plan["summary"]["review_cadence"] == "monthly"
    assert plan["summary"]["sensitive_data"] is True
    assert plan["summary"]["privileged_access"] is True
    assert plan["systems_in_scope"] == ["admin-api", "prod-db"]
    assert [role["name"] for role in plan["privileged_roles"]] == ["Owner", "ReadOnly", "Support Admin"]
    assert plan["exception_handling"]["maximum_age_days"] == 30
    assert plan["evidence"] == ["insight:iam-1"]


def test_access_review_plan_defaults_missing_optional_inputs() -> None:
    plan = generate_access_review_plan({})

    assert plan["summary"]["title"] == "Unknown"
    assert plan["summary"]["review_cadence"] == "quarterly"
    assert plan["privileged_roles"] == [{"name": "Unknown", "privileged": False}]
    assert plan["systems_in_scope"] == ["Unknown"]
    assert plan["approvers"] == ["Unknown"]


def test_access_review_plan_is_deterministic() -> None:
    payload = {"access": {"systems": ["z", "a", "z"], "privileged_roles": ["Viewer"]}}

    assert generate_access_review_plan(payload) == generate_access_review_plan(payload)
    assert generate_access_review_plan(payload)["systems_in_scope"] == ["a", "z"]

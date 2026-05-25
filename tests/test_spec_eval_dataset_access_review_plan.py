from __future__ import annotations

from max.spec.evaluation_dataset_access_review_plan import (
    generate_evaluation_dataset_access_review_plan,
)


def test_evaluation_dataset_access_review_plan_groups_access_by_dataset_and_role() -> None:
    plan = generate_evaluation_dataset_access_review_plan(
        {
            "datasets": [
                {"dataset": "safety eval", "classification": "restricted", "owner": "evals"},
                {"dataset": "privacy eval", "classification": "confidential", "owner": "privacy"},
            ],
            "access_entries": [
                {
                    "dataset": "safety eval",
                    "role": "reviewer",
                    "principal": "alice",
                    "privilege": "read",
                    "approval_status": "approved",
                    "owner": "evals",
                },
                {
                    "dataset": "safety eval",
                    "role": "reviewer",
                    "principal": "bob",
                    "privilege": "read",
                    "approval_status": "approved",
                    "owner": "evals",
                },
                {
                    "dataset": "privacy eval",
                    "role": "admin",
                    "principal": "analyst-group",
                    "privilege": "admin",
                    "approval_status": "stale",
                },
            ],
            "approval_evidence": ["access ticket export"],
            "recertification": ["quarterly data owner review"],
            "revocations": ["remove stale admin grants"],
            "monitoring": ["bulk export alert"],
        }
    )

    assert plan["title"] == "Evaluation Dataset Access Review Plan"
    assert [item["name"] for item in plan["access_by_dataset_role"]] == [
        "privacy eval / admin",
        "safety eval / reviewer",
    ]
    assert plan["access_by_dataset_role"][1]["principals"] == "alice, bob"
    assert {risk["gap"] for risk in plan["access_risks"]} == {
        "excessive privilege",
        "missing owner",
        "stale approval",
    }
    assert plan["revocation_schedule"][0]["name"] == "remove stale admin grants"
    assert plan["recertification_checkpoints"][0]["name"] == "quarterly data owner review"


def test_evaluation_dataset_access_review_plan_defaults_review_checkpoints() -> None:
    plan = generate_evaluation_dataset_access_review_plan({})

    assert plan["schema_version"] == "max.spec.evaluation_dataset_access_review_plan.v1"
    assert plan["summary"]["dataset_count"] == 1
    assert plan["dataset_inventory"][0]["dataset"] == "sensitive evaluation dataset"
    assert plan["access_by_dataset_role"][0]["name"] == "sensitive evaluation dataset / reviewer"
    assert plan["access_risks"][0]["gap"] == "missing owner"
    assert plan["revocation_schedule"]

from __future__ import annotations

import json

from max.spec.synthetic_data_usage_exception_plan import generate_synthetic_data_usage_exception_plan


def test_synthetic_data_usage_exception_plan_covers_controls_validation_and_evidence() -> None:
    plan = generate_synthetic_data_usage_exception_plan(
        _spec(
            {
                "exceptions": [
                    {
                        "scope": "support-ticket classifier training",
                        "owner": "ai_data_owner",
                        "expiry": "2026-08-01",
                        "generation_method": "template synthesis",
                    },
                    {"dataset": "billing demo records", "expiration": "2026-09-01"},
                ],
                "generation_method": [{"method": "differentially private tabular generator"}],
                "source_data_restrictions": ["no raw production identifiers"],
                "privacy_controls": [{"control": "k-anonymity review", "owner": "privacy"}],
                "validation_checks": [{"check": "distribution drift below threshold", "threshold": "5%"}],
                "expiry_review": ["monthly exception review"],
                "approval_criteria": ["privacy and data governance approval"],
                "verification_evidence": ["synthetic data validation report"],
            }
        )
    )

    assert plan["schema_version"] == "max.spec.synthetic_data_usage_exception_plan.v1"
    assert [item["name"] for item in plan["exception_scope"]] == [
        "billing demo records",
        "support-ticket classifier training",
    ]
    assert plan["exception_scope"][1]["owner"] == "ai_data_owner"
    assert plan["exception_scope"][1]["expiry"] == "2026-08-01"
    assert plan["privacy_controls"][0]["name"] == "k-anonymity review"
    assert plan["validation_checks"][0]["threshold"] == "5%"
    assert plan["verification_evidence"][0]["name"] == "synthetic data validation report"
    assert plan["evidence_references"][0]["reference"] == "signal:sd-1"
    assert json.loads(json.dumps(plan)) == plan


def test_synthetic_data_usage_exception_plan_allows_missing_optional_sections() -> None:
    plan = generate_synthetic_data_usage_exception_plan(_spec({"scopes": [{"use_case": "Demo Sandbox"}]}))

    assert plan["exception_scope"][0]["name"] == "Demo Sandbox"
    assert plan["exception_scope"][0]["expiry"] == "30 days"
    assert plan["generation_method"] == []
    assert plan["source_data_restrictions"] == []
    assert plan["privacy_controls"] == []
    assert plan["validation_checks"] == []
    assert plan["verification_evidence"] == []
    assert list(plan) == [
        "schema_version",
        "kind",
        "source",
        "summary",
        "exception_scope",
        "generation_method",
        "source_data_restrictions",
        "privacy_controls",
        "validation_checks",
        "expiry_review",
        "approval_criteria",
        "verification_evidence",
        "evidence_references",
    ]


def _spec(hints: dict) -> dict:
    return {"metadata": {"synthetic_data_usage_exception": hints}, "evidence": {"signal_ids": ["sd-1"]}}

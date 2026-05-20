from __future__ import annotations

from max.spec.privacy_review_readiness_plan import KIND, SCHEMA_VERSION, generate_privacy_review_readiness_plan


def test_privacy_review_readiness_plan_prioritizes_sensitive_data() -> None:
    plan = generate_privacy_review_readiness_plan(
        {
            "metadata": {
                "privacy_review_readiness": {
                    "data_categories": ["health data", "email"],
                    "user_populations": ["patients"],
                    "processors": [{"name": "AnalyticsCo", "owner": "vendor", "evidence": "DPA-42"}],
                    "retention": "90 days",
                    "consent": "explicit consent",
                }
            }
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["summary"]["sensitive_data"] is True
    assert plan["privacy_questions"][0]["priority"] == "critical"
    assert plan["launch_blockers"] == []


def test_privacy_review_readiness_plan_defaults_low_risk_inputs() -> None:
    plan = generate_privacy_review_readiness_plan({})

    assert plan["summary"]["sensitive_data"] is False
    assert plan["privacy_questions"][0]["priority"] == "medium"
    assert [gap["type"] for gap in plan["readiness_gaps"]] == ["retention", "consent"]
    assert plan["owners"][0] == {"role": "privacy_owner", "owner": "privacy_owner"}


def test_privacy_review_readiness_plan_preserves_processor_and_retention_evidence() -> None:
    plan = generate_privacy_review_readiness_plan(
        {
            "processors": [{"name": "EmailCo", "evidence": "DPA signed 2026-04-01"}],
            "retention": "delete after 30 days",
            "consent": "contract necessity",
            "evidence": {"source_idea_ids": ["privacy-1"]},
        }
    )

    assert plan["required_artifacts"][0]["description"] == "delete after 30 days"
    assert plan["required_artifacts"][2]["processor"] == "EmailCo"
    assert plan["required_artifacts"][2]["description"] == "DPA signed 2026-04-01"
    assert plan["required_artifacts"][2]["evidence_reference_ids"] == ["EV1"]

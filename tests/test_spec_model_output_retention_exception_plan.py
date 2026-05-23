from __future__ import annotations

from max.spec import generate_model_output_retention_exception_plan


def test_model_output_retention_exception_plan_covers_controls_and_expiry() -> None:
    plan = generate_model_output_retention_exception_plan(
        {
            "metadata": {
                "model_output_retention_exception": {
                    "categories": [{"category": "safety eval outputs", "model": "gpt-risk", "duration": "45 days"}],
                    "rationale": ["audit replay for disputed decisions"],
                    "redaction_controls": ["redact account identifiers"],
                    "access_review": ["privacy reviewer"],
                    "monitoring": ["daily retained output count"],
                    "expiry_workflow": ["purge after audit closure"],
                }
            }
        }
    )

    assert plan["retained_output_categories"][0]["name"] == "safety eval outputs"
    assert set(plan) >= {"exception_rationale", "retention_duration", "redaction_controls", "access_review", "monitoring", "expiry_workflow"}


def test_model_output_retention_exception_plan_defaults_duration_and_reviewers() -> None:
    plan = generate_model_output_retention_exception_plan({})

    assert plan["retained_output_categories"][0]["duration"] == "30 days"
    assert plan["access_review"][0]["name"] == "data owner, privacy, security, and model owner reviewers"

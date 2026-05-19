from __future__ import annotations

from max.spec.model_monitoring_plan import (
    generate_model_monitoring_plan,
    render_model_monitoring_plan_markdown,
)


def test_model_monitoring_classifies_and_sorts_model_states() -> None:
    plan = generate_model_monitoring_plan(
        {
            "project": {"title": "Recommendation Monitoring"},
            "models": [
                {"name": "ranking", "quality_score": 0.92, "drift_score": 0.05, "owner": "ml"},
                {"name": "summary", "quality_score": 0.84, "drift_score": 0.21, "owner": "nlp"},
                {"name": "fraud", "quality_score": 0.72, "drift_score": 0.15, "owner": "risk"},
            ],
        }
    )

    assert [row["name"] for row in plan["monitored_models"]] == ["fraud", "summary", "ranking"]
    assert [row["state"] for row in plan["monitored_models"]] == ["rollback_needed", "degraded", "normal"]
    assert plan["summary"]["rollback_needed_count"] == 1
    assert plan["summary"]["degraded_count"] == 1


def test_model_monitoring_includes_thresholds_datasets_and_actions() -> None:
    plan = generate_model_monitoring_plan(
        {
            "models": [{"name": "ranking", "state": "normal"}],
            "quality_metrics": [{"name": "precision", "threshold": ">= 0.91"}],
            "evaluation_datasets": ["golden set", "shadow traffic"],
        }
    )

    assert plan["metric_thresholds"] == [{"id": "MET1", "name": "precision", "threshold": ">= 0.91", "owner": "model_owner"}]
    assert plan["evaluation_datasets"] == ["golden set", "shadow traffic"]
    assert plan["owner_actions"][0]["action"] == "model_owner reviews ranking state: normal."


def test_model_monitoring_markdown_has_required_sections() -> None:
    plan = generate_model_monitoring_plan(
        {
            "project": {"title": "Recommendation Monitoring"},
            "models": [{"name": "fraud", "quality_score": 0.72, "drift_score": 0.15, "owner": "risk"}],
            "human_review_steps": ["risk reviewer approves fraud model restart"],
            "evidence": {"insight_ids": ["model-1"]},
        }
    )

    first = render_model_monitoring_plan_markdown(plan)
    second = render_model_monitoring_plan_markdown(plan)

    assert first == second
    assert first.startswith("# Recommendation Monitoring Model Monitoring Plan")
    assert "## Monitoring Matrix" in first
    assert "rollback_needed" in first
    assert "## Drift Response" in first
    assert "Rollback model or disable automated decisions" in first
    assert "## Evaluation Cadence" in first
    assert "## Human Review" in first
    assert "insight:model-1" in first

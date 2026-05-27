from __future__ import annotations

import json

from max.spec.model_retirement_plan import generate_model_retirement_plan


def test_model_retirement_plan_builds_complete_plan() -> None:
    plan = generate_model_retirement_plan(
        _spec(
            "model_retirement",
            {
                "owner": "ml owner",
                "replacement_model": "gpt-next",
                "evaluation_evidence": "eval-run-42",
                "impacted_workflows": [{"workflow": "support triage", "impact": "routing"}],
                "migration_checkpoints": ["shadow run"],
                "archive_requirements": ["model card archived"],
            },
        )
    )

    assert plan["kind"] == "max.spec.model_retirement_plan"
    assert plan["replacement_model"]["name"] == "gpt-next"
    assert plan["impacted_workflows"][0]["name"] == "support triage"
    assert plan["migration_checkpoints"][0]["name"] == "shadow run"
    assert plan["archive_requirements"][0]["name"] == "model card archived"
    assert plan["blockers"] == []


def test_model_retirement_plan_flags_missing_replacement_and_owner() -> None:
    plan = generate_model_retirement_plan(_spec("model_retirement", {}))

    assert [item["name"] for item in plan["blockers"]] == [
        "missing replacement model",
        "missing retirement owner",
        "missing evaluation evidence",
    ]


def test_model_retirement_plan_warns_on_stale_evaluation() -> None:
    plan = generate_model_retirement_plan(
        _spec(
            "model_retirement",
            {
                "owner": "ml owner",
                "replacement_model": "gpt-next",
                "evaluation_evidence": "eval-run-42",
                "evaluation_freshness": "stale",
            },
        )
    )

    assert plan["warnings"][0]["name"] == "stale evaluation evidence"
    assert "replacement model evaluation evidence attached" in {
        item["name"] for item in plan["validation_checks"]
    }


def test_model_retirement_plan_preserves_metadata_and_is_deterministic() -> None:
    payload = _spec(
        "model_retirement",
        {"owner": "ml owner", "replacement_model": "gpt-next", "evaluation_evidence": "eval-run-42"},
    )
    plan = generate_model_retirement_plan(payload)

    assert plan == generate_model_retirement_plan(payload)
    assert json.loads(json.dumps(plan)) == plan
    assert plan["source"]["idea_id"] == "idea-1"
    assert plan["evidence_references"][0]["reference"] == "signal:sig-1"


def _spec(key: str, hints: dict) -> dict:
    return {"source": {"idea_id": "idea-1"}, "metadata": {key: hints}, "evidence": {"signal_ids": ["sig-1"]}}

from __future__ import annotations

import pytest

from max.spec.prompt_evaluation_regression_triage_plan import generate_prompt_evaluation_regression_triage_plan


def _spec(severity: str = "critical") -> dict:
    return {
        "metadata": {
            "prompt_evaluation_regression_triage": {
                "prompt_name": "summarizer",
                "prompt_version": "2026.06",
                "baseline_version": "2026.05",
                "failed_metrics": ["faithfulness", "toxicity", "faithfulness"],
                "affected_profiles": ["sales", "support"],
                "owner": "eval_owner",
                "severity": severity,
            }
        }
    }


def test_prompt_evaluation_regression_triage_sorts_metrics_and_gates_critical() -> None:
    plan = generate_prompt_evaluation_regression_triage_plan(_spec())

    assert [item["metric"] for item in plan["metric_triage"]] == ["faithfulness", "toxicity"]
    assert plan["release_gate"][0]["name"] == "Immediate release gate"
    assert plan["release_gate"][0]["severity"] == "critical"


def test_prompt_evaluation_regression_triage_standard_and_validation() -> None:
    plan = generate_prompt_evaluation_regression_triage_plan(_spec("medium"))

    assert [item["name"] for item in plan["release_gate"]] == ["Release gate approval"]
    with pytest.raises(ValueError, match="failed_metrics"):
        generate_prompt_evaluation_regression_triage_plan({"metadata": {"prompt_evaluation_regression_triage": {"prompt_name": "summarizer"}}})

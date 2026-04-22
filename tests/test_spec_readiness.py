"""Tests for tact spec readiness evaluation."""

from __future__ import annotations

from max.spec.readiness import evaluate_spec_readiness
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def test_spec_readiness_ready_unit_passes(sample_unit, sample_evaluation):
    readiness = evaluate_spec_readiness(sample_unit, sample_evaluation)

    assert readiness["idea_id"] == "bu-test001"
    assert readiness["score"] == 100.0
    assert readiness["status"] == "pass"
    assert readiness["passed"] is True
    assert readiness["failed_check_ids"] == []
    assert readiness["remediation"] == "Ready to generate a tact spec."


def test_spec_readiness_incomplete_unit_fails_actionably():
    unit = BuildableUnit(
        id="bu-incomplete",
        title="Incomplete Idea",
        one_liner="Too thin",
        category=BuildableCategory.APPLICATION,
        problem="Vague problem",
        solution="Vague solution",
        value_proposition="Value",
    )

    readiness = evaluate_spec_readiness(unit)

    assert readiness["score"] == 0.0
    assert readiness["status"] == "fail"
    assert readiness["passed"] is False
    assert readiness["failed_check_ids"] == [
        "problem_clarity",
        "target_user",
        "validation_plan",
        "evidence_count_diversity",
        "risks",
        "stack_specificity",
        "evaluation_recommendation",
    ]
    assert "Clarify the problem" in readiness["remediation"]
    assert "Run utility evaluation" in readiness["remediation"]
    assert all(check["remediation"] for check in readiness["checks"])

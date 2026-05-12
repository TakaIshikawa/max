"""Tests for vendor evaluation export."""

from __future__ import annotations

import csv
import io
import json

from max.exports.vendor_evaluation import (
    CRITERIA,
    KIND,
    SCHEMA_VERSION,
    EvaluationCriterion,
    build_vendor_evaluation,
    render_vendor_evaluation_csv,
    render_vendor_evaluation_json,
    render_vendor_evaluation_markdown,
)


def _unit() -> dict:
    return {
        "id": "bu-build001",
        "title": "Agent Support Console",
        "summary": "A tailored support workflow for agent operations.",
        "scores": {
            EvaluationCriterion.FUNCTIONALITY_FIT.value: 92,
            EvaluationCriterion.INTEGRATION_EASE.value: 68,
            EvaluationCriterion.TOTAL_COST.value: 58,
            EvaluationCriterion.VENDOR_STABILITY.value: 66,
            EvaluationCriterion.CUSTOMIZABILITY.value: 95,
            EvaluationCriterion.SUPPORT_QUALITY.value: 55,
            EvaluationCriterion.SECURITY_COMPLIANCE.value: 72,
            EvaluationCriterion.SCALABILITY.value: 74,
        },
    }


def _vendors() -> list[dict]:
    return [
        {
            "id": "ven-suite",
            "name": "SuiteDesk",
            "description": "Enterprise support suite.",
            "scores": {
                EvaluationCriterion.FUNCTIONALITY_FIT.value: 76,
                EvaluationCriterion.INTEGRATION_EASE.value: 84,
                EvaluationCriterion.TOTAL_COST.value: 72,
                EvaluationCriterion.VENDOR_STABILITY.value: 88,
                EvaluationCriterion.CUSTOMIZABILITY.value: 54,
                EvaluationCriterion.SUPPORT_QUALITY.value: 86,
                EvaluationCriterion.SECURITY_COMPLIANCE.value: 90,
                EvaluationCriterion.SCALABILITY.value: 88,
            },
        },
        {
            "id": "ven-platform",
            "name": "WorkflowBase",
            "description": "Configurable workflow platform.",
            "scores": {
                EvaluationCriterion.FUNCTIONALITY_FIT.value: 86,
                EvaluationCriterion.INTEGRATION_EASE.value: 82,
                EvaluationCriterion.TOTAL_COST.value: 78,
                EvaluationCriterion.VENDOR_STABILITY.value: 80,
                EvaluationCriterion.CUSTOMIZABILITY.value: 82,
                EvaluationCriterion.SUPPORT_QUALITY.value: 76,
                EvaluationCriterion.SECURITY_COMPLIANCE.value: 86,
                EvaluationCriterion.SCALABILITY.value: 84,
            },
        },
    ]


def test_build_vendor_evaluation_with_multiple_vendors() -> None:
    evaluation = build_vendor_evaluation(_unit(), _vendors())

    assert evaluation["schema_version"] == SCHEMA_VERSION
    assert evaluation["kind"] == KIND
    assert len(evaluation["criteria"]) == 8
    assert [criterion.value for criterion in CRITERIA] == [
        "functionality_fit",
        "integration_ease",
        "total_cost",
        "vendor_stability",
        "customizability",
        "support_quality",
        "security_compliance",
        "scalability",
    ]
    assert evaluation["build_option"]["name"] == "Agent Support Console"
    assert [vendor["name"] for vendor in evaluation["vendor_options"]] == ["SuiteDesk", "WorkflowBase"]
    assert len(evaluation["comparison_matrix"]) == 8
    assert evaluation["comparison_matrix"][0]["scores"]["WorkflowBase"] == 86.0
    assert evaluation["recommendation"]["decision"] in {"build", "buy", "hybrid"}
    assert evaluation["decision_factors"]


def test_no_alternatives_defaults_to_build_recommendation() -> None:
    evaluation = build_vendor_evaluation(_unit(), [])

    assert evaluation["vendor_options"] == []
    assert evaluation["recommendation"]["decision"] == "build"
    assert evaluation["recommendation"]["winning_option"] == "Agent Support Console"
    assert "No vendor alternatives" in evaluation["recommendation"]["justification"]


def test_weighted_scoring_calculation() -> None:
    evaluation = build_vendor_evaluation(
        {
            "title": "Flat Build",
            "scores": {criterion.value: 50 for criterion in CRITERIA},
        },
        [
            {
                "name": "Flat Vendor",
                "scores": {criterion.value: 80 for criterion in CRITERIA},
            }
        ],
    )

    assert evaluation["weighted_scores"]["Flat Build"] == 50.0
    assert evaluation["weighted_scores"]["Flat Vendor"] == 80.0
    assert evaluation["recommendation"]["decision"] == "buy"
    assert evaluation["recommendation"]["winning_option"] == "Flat Vendor"


def test_render_formats_are_stable() -> None:
    evaluation = build_vendor_evaluation(_unit(), _vendors())

    markdown = render_vendor_evaluation_markdown(evaluation)
    rendered_json = render_vendor_evaluation_json(evaluation)
    rendered_csv = render_vendor_evaluation_csv(evaluation)

    payload = json.loads(rendered_json)
    rows = list(csv.DictReader(io.StringIO(rendered_csv)))

    assert markdown.startswith("# Vendor Evaluation: Agent Support Console")
    assert "| Criterion | Weight | Agent Support Console | SuiteDesk | WorkflowBase |" in markdown
    assert "## Decision Factors" in markdown
    assert payload["kind"] == KIND
    assert payload["source"]["idea_id"] == "bu-build001"
    assert rows[0]["criterion"] == EvaluationCriterion.FUNCTIONALITY_FIT.value
    assert rows[-1]["criterion"] == "weighted_total"
    assert rows[-1]["WorkflowBase"] == str(evaluation["weighted_scores"]["WorkflowBase"])

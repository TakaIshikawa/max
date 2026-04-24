"""Tests for acceptance criteria generation."""

from __future__ import annotations

import json

from max.spec.acceptance_criteria import (
    ACCEPTANCE_CRITERIA_SCHEMA_VERSION,
    generate_acceptance_criteria,
)


def test_generate_acceptance_criteria_is_deterministic(sample_unit, sample_evaluation):
    evidence_density = {
        "density_score": 72.5,
        "missing_evidence_warnings": [],
    }

    first = generate_acceptance_criteria(sample_unit, sample_evaluation, evidence_density)
    second = generate_acceptance_criteria(sample_unit, sample_evaluation, evidence_density)

    assert first == second
    assert first["schema_version"] == ACCEPTANCE_CRITERIA_SCHEMA_VERSION
    assert first["kind"] == "max.acceptance_criteria"
    assert first["idea_id"] == "bu-test001"
    assert first["summary"]["recommendation"] == "yes"
    assert [item["id"] for item in first["functional_criteria"]] == [
        "AC-F1",
        "AC-F2",
        "AC-F3",
        "AC-F4",
        "AC-F5",
        "AC-F6",
    ]
    assert [item["id"] for item in first["non_functional_criteria"]] == [
        "AC-NF1",
        "AC-NF2",
        "AC-NF3",
        "AC-NF4",
        "AC-NF5",
    ]
    assert any(item["id"] == "EC6" for item in first["edge_cases"])
    assert {"type": "insight", "id": "ins-test001", "uri": "insights://ins-test001"} in first["evidence_links"]
    assert {"type": "signal", "id": "sig-test001", "uri": "signals://sig-test001"} in first["evidence_links"]
    assert any("Niche audience" in item for item in first["out_of_scope"])


def test_generate_acceptance_criteria_handles_sparse_idea(sample_unit):
    sparse_unit = sample_unit.model_copy(
        update={
            "specific_user": "",
            "validation_plan": "",
            "inspiring_insights": [],
            "evidence_signals": [],
            "domain_risks": [],
            "composability_notes": "",
        }
    )

    criteria = generate_acceptance_criteria(sparse_unit)

    assert criteria["summary"]["recommendation"] is None
    assert len(criteria["evidence_links"]) == 0
    assert any(edge_case["id"] == "EC4" for edge_case in criteria["edge_cases"])
    assert json.loads(json.dumps(criteria))["kind"] == "max.acceptance_criteria"

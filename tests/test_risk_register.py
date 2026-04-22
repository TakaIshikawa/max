"""Tests for deterministic risk register generation."""

from __future__ import annotations

from datetime import datetime, timezone

from max.spec import generate_risk_register


def test_risk_register_prioritizes_core_risk_inputs(sample_unit, sample_evaluation):
    unit = sample_unit.model_copy(
        update={
            "specific_user": "",
            "buyer": "",
            "workflow_context": "",
            "domain_risks": ["protocol churn could break implementations"],
        }
    )
    evaluation = sample_evaluation.model_copy(
        update={
            "pain_severity": sample_evaluation.pain_severity.model_copy(update={"value": 4.5}),
            "weaknesses": ["Niche audience"],
        }
    )
    evidence_density = {
        "density_score": 24.0,
        "average_credibility": 0.4,
        "newest_evidence_timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
        "missing_evidence_warnings": ["Missing evidence signal(s): sig-missing"],
    }
    contradictions = {
        "contradiction_count": 1,
        "contradictions": [
            {
                "claim": "MCP users need testing",
                "severity": "high",
                "involved_signal_ids": ["sig-a", "sig-b"],
                "suggested_review_note": "Review high-severity conflict on MCP users need testing.",
            }
        ],
    }

    register = generate_risk_register(unit, evaluation, evidence_density, contradictions)

    assert register["schema_version"] == "max-risk-register/v1"
    assert register["kind"] == "max.risk_register"
    assert register["idea_id"] == "bu-test001"
    risk_ids = [risk["id"] for risk in register["risks"]]
    assert "contradiction_1" in risk_ids
    assert "missing_specific_user" in risk_ids
    assert "missing_buyer" in risk_ids
    assert "missing_workflow_context" in risk_ids
    assert "domain_risk_1" in risk_ids
    assert "low_pain_severity" in risk_ids
    assert "evaluation_weakness_1" in risk_ids
    assert "weak_evidence_density" in risk_ids
    assert "low_evidence_credibility" in risk_ids
    assert "stale_evidence" in risk_ids
    assert [risk["priority"] for risk in register["risks"]] == list(range(1, len(register["risks"]) + 1))
    assert register["risks"][0]["severity"] == "critical"
    assert all(risk["owner_suggestion"] for risk in register["risks"])
    assert all(risk["validation_trigger"] for risk in register["risks"])


def test_risk_register_reports_missing_evaluation_and_thin_evidence(sample_unit):
    unit = sample_unit.model_copy(
        update={
            "inspiring_insights": [],
            "evidence_signals": [],
            "source_idea_ids": [],
            "domain_risks": [],
        }
    )

    register = generate_risk_register(unit)

    risk_ids = {risk["id"] for risk in register["risks"]}
    assert "missing_evaluation" in risk_ids
    assert "thin_evidence" in risk_ids
    assert register["source"]["evaluation_available"] is False
    assert register["source"]["evidence_density_available"] is False

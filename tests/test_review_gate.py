"""Tests for risk-aware review gate decisions."""

from __future__ import annotations

from max.analysis.review_gate import build_review_gate_decision
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


def _dim(value: float = 8.0, confidence: float = 0.8) -> DimensionScore:
    return DimensionScore(value=value, confidence=confidence, reasoning="test")


def _evaluation(
    unit_id: str,
    *,
    score: float = 82.0,
    recommendation: str = "yes",
    build_effort: float = 8.0,
) -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_dim(8.0),
        addressable_scale=_dim(8.0),
        build_effort=_dim(build_effort),
        composability=_dim(8.0),
        competitive_density=_dim(8.0),
        timing_fit=_dim(8.0),
        compounding_value=_dim(8.0),
        overall_score=score,
        recommendation=recommendation,
    )


def _unit(
    unit_id: str,
    *,
    prior_art_status: str = "clear",
    domain_risks: list[str] | None = None,
    complete: bool = True,
    category: str = BuildableCategory.CLI_TOOL,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Review Gate Idea {unit_id}",
        one_liner="A focused local review helper",
        category=category,
        problem=(
            "Reviewers lack a simple deterministic gate before approving implementation."
            if complete
            else "Unclear."
        ),
        solution=(
            "Provide a local command that combines readiness, risk, and evaluation signals."
            if complete
            else "Build it."
        ),
        target_users="humans",
        value_proposition=(
            "Review decisions become consistent and auditable."
            if complete
            else "Better."
        ),
        specific_user="product reviewer" if complete else "",
        buyer="product lead" if complete else "",
        workflow_context="weekly product review queue" if complete else "",
        validation_plan="Review five approved ideas and compare the gate to human decisions."
        if complete
        else "",
        domain_risks=domain_risks if domain_risks is not None else ["review policy drift"],
        evidence_rationale="Signals and insight both point to review inconsistency."
        if complete
        else "",
        inspiring_insights=["ins-1"] if complete else [],
        evidence_signals=["sig-1"] if complete else [],
        tech_approach="Small Python module and CLI command with deterministic scoring."
        if complete
        else "",
        suggested_stack={"language": "python", "runtime": "cli"} if complete else {},
        prior_art_status=prior_art_status,
        domain="testing",
    )


def _insert(store: Store, unit: BuildableUnit, evaluation: UtilityEvaluation | None) -> None:
    store.insert_buildable_unit(unit)
    if evaluation is not None:
        store.insert_evaluation(evaluation)


def test_review_gate_approves_ready_low_risk_idea(store: Store) -> None:
    unit = _unit("bu-approve")
    _insert(store, unit, _evaluation(unit.id, score=84.0))

    decision = build_review_gate_decision(store, unit.id)

    assert decision.decision == "approve"
    assert not decision.blocking_reasons
    assert not decision.warnings
    assert {item.source for item in decision.evidence_used} == {
        "utility_evaluation",
        "spec_readiness",
        "risk_register",
        "prior_art",
        "blast_radius",
    }


def test_review_gate_needs_revision_for_warning_only_idea(store: Store) -> None:
    unit = _unit("bu-revise", prior_art_status="weak_match")
    _insert(store, unit, _evaluation(unit.id, score=82.0))

    decision = build_review_gate_decision(store, unit.id)

    assert decision.decision == "needs_revision"
    assert not decision.blocking_reasons
    assert any("prior art has weak matches" in warning for warning in decision.warnings)


def test_review_gate_holds_low_readiness_even_with_high_score(store: Store) -> None:
    unit = _unit("bu-low-ready", complete=False, prior_art_status="clear")
    _insert(store, unit, _evaluation(unit.id, score=94.0, recommendation="strong_yes"))

    decision = build_review_gate_decision(store, unit.id)

    assert decision.decision == "hold"
    assert any("spec readiness" in reason for reason in decision.blocking_reasons)


def test_review_gate_holds_high_risk_even_with_high_score(store: Store) -> None:
    unit = _unit(
        "bu-high-risk",
        domain_risks=[
            "privacy compliance",
            "billing compliance",
            "security audit",
            "financial controls",
        ],
        category=BuildableCategory.APPLICATION,
    )
    _insert(store, unit, _evaluation(unit.id, score=95.0, recommendation="strong_yes"))

    decision = build_review_gate_decision(store, unit.id)

    assert decision.decision == "hold"
    assert any("risk" in reason for reason in decision.blocking_reasons)


def test_review_gate_rejects_low_evaluation_score(store: Store) -> None:
    unit = _unit("bu-reject")
    _insert(store, unit, _evaluation(unit.id, score=42.0, recommendation="no"))

    decision = build_review_gate_decision(store, unit.id)

    assert decision.decision == "reject"
    assert any("evaluation" in reason for reason in decision.blocking_reasons)


def test_review_gate_handles_missing_optional_data(store: Store) -> None:
    unit = _unit("bu-missing-data", prior_art_status="unchecked")
    _insert(store, unit, None)

    decision = build_review_gate_decision(store, unit.id)

    assert decision.decision == "hold"
    assert any("utility evaluation is missing" == reason for reason in decision.blocking_reasons)
    assert any(item.source == "utility_evaluation" and item.status == "missing" for item in decision.evidence_used)


def test_review_gate_is_deterministic_for_identical_store_data(store: Store) -> None:
    unit = _unit("bu-deterministic", prior_art_status="weak_match")
    _insert(store, unit, _evaluation(unit.id, score=82.0))

    first = build_review_gate_decision(store, unit.id)
    second = build_review_gate_decision(store, unit.id)

    assert first == second


def test_review_gate_unknown_idea_raises_value_error(store: Store) -> None:
    try:
        build_review_gate_decision(store, "bu-missing")
    except ValueError as exc:
        assert "Idea not found: bu-missing" in str(exc)
    else:
        raise AssertionError("expected ValueError")

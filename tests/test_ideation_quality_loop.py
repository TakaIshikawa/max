"""Tests for domain-focused ideation quality loop helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from max.ideation.critique import IdeaCritique, apply_critiques
from max.ideation.evidence import build_evidence_pack
from max.ideation.quality_gate import quality_gate
from max.profiles.schema import DomainContext
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def _unit(**kw) -> BuildableUnit:
    defaults = dict(
        title="Prior Auth Work Queue",
        one_liner="Find stuck prior authorizations",
        category="workflow_automation",
        problem="Clinic staff lose hours tracking prior authorizations.",
        solution="Monitor payer status and flag stale requests.",
        value_proposition="Reduces admin follow-up time.",
        specific_user="prior authorization coordinator",
        buyer="clinic administrator",
        workflow_context="daily review of unresolved authorization requests",
        current_workaround="spreadsheet and payer portal checks",
        why_now="more payer portals and staffing pressure",
        validation_plan="shadow two coordinators for one week",
        evidence_rationale="Repeated problem signals from clinic operations.",
        inspiring_insights=["ins-1"],
    )
    defaults.update(kw)
    return BuildableUnit(**defaults)


def _signal(id: str, role: str) -> Signal:
    return Signal(
        id=id,
        source_type=SignalSourceType.FORUM,
        source_adapter="reddit",
        title=f"{role} signal",
        content=f"{role} content",
        url=f"https://example.com/{id}",
        credibility=0.8,
        metadata={"signal_role": role},
    )


def test_build_evidence_pack_includes_domain_and_role_signals():
    domain = DomainContext(
        name="healthcare",
        description="Healthcare",
        categories=["workflow_automation"],
        target_user_types=["clinicians"],
        target_segments=["small clinics"],
        workflows=["prior authorization"],
        buyer_roles=["clinic administrator"],
        hard_constraints=["HIPAA"],
        bad_idea_patterns=["generic AI assistant"],
        good_idea_criteria=["clear buyer"],
    )
    insight = Insight(
        id="ins-1",
        category=InsightCategory.GAP,
        title="Prior auth pain",
        summary="Manual tracking is painful.",
        evidence=["sig-1"],
        confidence=0.8,
        domains=["healthcare"],
    )
    store = MagicMock()
    store.get_signals.return_value = [
        _signal("sig-1", "problem"),
        _signal("sig-2", "solution"),
        _signal("sig-3", "market"),
    ]
    store.get_feedback_log.return_value = [
        {"title": "Generic doctor assistant", "reason": "too vague", "outcome": "rejected"},
        {"title": "Prior auth queue", "reason": "clear buyer", "outcome": "approved"},
    ]

    pack = build_evidence_pack(insights=[insight], store=store, domain=domain)

    assert pack.domain_name == "healthcare"
    assert pack.target_segments == ["small clinics"]
    assert len(pack.problem_signals) == 1
    assert len(pack.solution_signals) == 1
    assert len(pack.market_signals) == 1
    assert "Generic doctor assistant: too vague" in pack.rejected_patterns
    assert "Prior auth queue: clear buyer" in pack.successful_patterns


def test_apply_critiques_sets_quality_scores():
    unit = _unit()
    critique = IdeaCritique(
        title=unit.title,
        urgency=8,
        buyer_clarity=9,
        specificity=8,
        evidence_support=7,
        feasibility=8,
        differentiation=6,
        distribution_path=7,
        domain_risk=7,
        novelty=6,
        usefulness=9,
    )

    [updated] = apply_critiques([unit], [critique])

    assert updated.novelty_score == 6
    assert updated.usefulness_score == 9
    assert updated.quality_score > 7


def test_quality_gate_rejects_missing_buyer_specificity():
    vague = _unit(buyer="", workflow_context="")

    kept, rejected = quality_gate([vague])

    assert kept == []
    assert rejected == [vague]
    assert "insufficient_specificity" in vague.rejection_tags


def test_quality_gate_keeps_specific_evidence_backed_unit():
    unit = _unit(quality_score=7.5)

    kept, rejected = quality_gate([unit])

    assert kept == [unit]
    assert rejected == []

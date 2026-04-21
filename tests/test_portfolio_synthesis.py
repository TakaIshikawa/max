from __future__ import annotations

from max.analysis.portfolio_synthesis import (
    build_candidates,
    render_markdown,
    synthesize_project_briefs,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


def _unit(
    unit_id: str,
    *,
    title: str,
    domain: str = "developer-tools",
    status: str = "approved",
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner="Adversarial workflow benchmark for tool-using agents",
        category="eval_framework",
        problem="Teams cannot test agent security and workflow capability together.",
        solution="Run workflow fixtures with embedded attack payloads and score both capability and safety.",
        value_proposition="Ship safer agents without blocking useful workflows.",
        specific_user="platform engineer deploying AI agents",
        buyer="engineering manager",
        workflow_context="CI gate before agent production deployment",
        current_workaround="Manual prompt testing",
        why_now="MCP adoption makes agent tool security urgent.",
        validation_plan="Run against three agent frameworks and publish scorecards.",
        first_10_customers="Agent framework maintainers and platform teams",
        tech_approach="Python package with YAML fixtures and CLI runner",
        domain=domain,
        status=status,
        quality_score=7.5,
        domain_risks=["Framework adapters may change quickly"],
    )


def _evaluation(unit_id: str, score: float = 72.0) -> UtilityEvaluation:
    dim = DimensionScore(value=7.0, confidence=0.8, reasoning="good")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=DimensionScore(value=8.0, confidence=0.8, reasoning="small MVP"),
        composability=dim,
        competitive_density=dim,
        timing_fit=dim,
        compounding_value=dim,
        overall_score=score,
        recommendation="yes",
    )


def test_build_candidates_filters_to_approved_and_scores_readiness() -> None:
    approved = _unit("bu-1", title="AgentAdversarialBench")
    rejected = _unit("bu-2", title="Rejected Agent Tool", status="rejected")

    candidates = build_candidates(
        [approved, rejected],
        evaluations={"bu-1": _evaluation("bu-1"), "bu-2": _evaluation("bu-2")},
        feedback={"bu-1": {"approval_score": 8}, "bu-2": {"approval_score": 1}},
    )

    assert [candidate.unit.id for candidate in candidates] == ["bu-1"]
    assert candidates[0].readiness_score > 80
    assert "clear buyer" in candidates[0].strengths


def test_synthesize_project_briefs_groups_candidates_by_theme() -> None:
    first = _unit("bu-1", title="AgentAdversarialBench")
    second = _unit("bu-2", title="AgentAPIProbe")

    candidates = build_candidates(
        [first, second],
        evaluations={"bu-1": _evaluation("bu-1", 75), "bu-2": _evaluation("bu-2", 70)},
        feedback={"bu-1": {"approval_score": 8}, "bu-2": {"approval_score": 6}},
    )
    briefs = synthesize_project_briefs(candidates, top=3)

    assert len(briefs) == 1
    assert briefs[0].theme == "agent-security-evaluation"
    assert briefs[0].lead.unit.id == "bu-1"
    assert briefs[0].supporting[0].unit.id == "bu-2"
    assert "bu-1" in briefs[0].source_idea_ids


def test_render_markdown_includes_design_sections() -> None:
    unit = _unit("bu-1", title="AgentAdversarialBench")
    candidates = build_candidates(
        [unit],
        evaluations={"bu-1": _evaluation("bu-1")},
        feedback={"bu-1": {"approval_score": 8}},
    )
    markdown = render_markdown(synthesize_project_briefs(candidates))

    assert "# Design Candidates" in markdown
    assert "### MVP Scope" in markdown
    assert "### First Milestones" in markdown
    assert "`bu-1`" in markdown


def test_store_persists_design_brief_with_sources(tmp_path) -> None:
    first = _unit("bu-1", title="AgentAdversarialBench")
    second = _unit("bu-2", title="AgentAPIProbe")
    candidates = build_candidates(
        [first, second],
        evaluations={"bu-1": _evaluation("bu-1", 75), "bu-2": _evaluation("bu-2", 70)},
        feedback={"bu-1": {"approval_score": 8}, "bu-2": {"approval_score": 6}},
    )
    brief = synthesize_project_briefs(candidates, top=1)[0]

    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = store.insert_design_brief(brief)
        stored = store.get_design_brief(brief_id)
        assert stored is not None
        assert stored["lead_idea_id"] == "bu-1"
        assert stored["design_status"] == "candidate"
        assert stored["source_idea_ids"] == ["bu-1", "bu-2"]
        roles = {(source["idea_id"], source["role"]) for source in stored["sources"]}
        assert ("bu-1", "lead") in roles
        assert ("bu-2", "supporting") in roles

        store.update_design_brief_status(brief_id, "designing")
        assert store.get_design_brief(brief_id)["design_status"] == "designing"
    finally:
        store.close()

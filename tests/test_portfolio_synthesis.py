from __future__ import annotations

from max.analysis.portfolio_synthesis import (
    build_candidates,
    render_design_brief_markdown,
    render_markdown,
    synthesize_project_briefs,
)
from max.analysis.blueprint_export import SCHEMA_VERSION, build_blueprint_source_brief
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


def test_render_design_brief_markdown_from_persisted_dict() -> None:
    markdown = render_design_brief_markdown(
        {
            "title": "Persisted Brief",
            "domain": "testing",
            "theme": "api-testing",
            "readiness_score": 82.0,
            "lead_idea_id": "bu-1",
            "buyer": "Platform lead",
            "specific_user": "API maintainer",
            "workflow_context": "Exporting briefs",
            "why_this_now": "Teams need design handoff packets.",
            "merged_product_concept": "A Markdown handoff.",
            "synthesis_rationale": "Single strong source.",
            "mvp_scope": ["Render Markdown"],
            "first_milestones": ["Add API endpoint"],
            "validation_plan": "Call the endpoint.",
            "risks": ["Missing source title"],
            "source_idea_ids": ["bu-1"],
            "sources": [{"idea_id": "bu-2", "role": "supporting", "rank": 1}],
        }
    )

    assert "# Persisted Brief" in markdown
    assert "- **Lead idea**: `bu-1` — Persisted Brief" in markdown
    assert "### MVP Scope" in markdown
    assert "- Render Markdown" in markdown
    assert "- `bu-2`" in markdown


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


def test_blueprint_export_includes_design_brief_and_source_ideas(tmp_path) -> None:
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
        store.insert_buildable_unit(first)
        store.insert_buildable_unit(second)
        store.insert_evaluation(_evaluation("bu-1", 75))
        store.insert_feedback("bu-1", "approved", "strong candidate", approval_score=8)
        brief_id = store.insert_design_brief(brief)
        stored = store.get_design_brief(brief_id)

        packet = build_blueprint_source_brief(
            store,
            stored,
            exported_at="2026-04-22T00:00:00+00:00",
        )

        assert packet["schema_version"] == SCHEMA_VERSION
        assert packet["source"]["project"] == "max"
        assert packet["source"]["id"] == brief_id
        assert packet["design_brief"]["title"] == "AgentAdversarialBench"
        assert packet["design_brief"]["source_idea_ids"] == ["bu-1", "bu-2"]
        lead = next(item for item in packet["source_ideas"] if item["role"] == "lead")
        assert lead["id"] == "bu-1"
        assert lead["evaluation_score"] == 75
        assert lead["feedback_outcome"] == "approved"
        assert packet["blueprint_import_hints"]["recommended_source_priority"] == "design_brief"
    finally:
        store.close()


def test_blueprint_export_marks_missing_source_ideas(tmp_path) -> None:
    first = _unit("bu-1", title="AgentAdversarialBench")
    candidates = build_candidates(
        [first],
        evaluations={"bu-1": _evaluation("bu-1")},
        feedback={"bu-1": {"approval_score": 8}},
    )
    brief = synthesize_project_briefs(candidates, top=1)[0]

    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = store.insert_design_brief(brief)
        packet = build_blueprint_source_brief(store, store.get_design_brief(brief_id))
        assert packet["source_ideas"][0]["id"] == "bu-1"
        assert packet["source_ideas"][0]["missing"] is True
    finally:
        store.close()

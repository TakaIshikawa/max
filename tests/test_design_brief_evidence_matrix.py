from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.design_brief_evidence_matrix import (
    CLAIM_AREAS,
    SCHEMA_VERSION,
    build_design_brief_evidence_matrix,
    render_design_brief_evidence_matrix,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


CSV_HEADER = (
    "design_brief_id,design_brief_title,claim_id,claim,evidence_id,source_type,"
    "source_title,strength,confidence,contradiction_flag,notes\n"
)


def _signal(signal_id: str, adapter: str, role: str, *, source_type=SignalSourceType.FORUM) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=adapter,
        title=f"{role.title()} signal",
        content=f"Persisted {role} evidence",
        url=f"https://example.com/{signal_id}",
        tags=[role],
        credibility=0.8,
        metadata={"signal_role": role},
    )


def _unit(
    unit_id: str,
    *,
    insight_ids: list[str],
    signal_ids: list[str],
    title: str = "Agent Workflow Guard",
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner="Evidence-backed agent workflow release checks",
        category="application",
        problem="Platform teams cannot prove agent workflow safety before release.",
        solution="Run workflow fixtures with risk checks and release gates.",
        value_proposition="Reduce unsafe agent releases without slowing useful workflows.",
        specific_user="platform engineer deploying AI agents",
        buyer="engineering manager",
        workflow_context="CI gate before agent production deployment",
        current_workaround="manual prompt testing and spreadsheet review",
        why_now="Agent tool use is moving into production workflows.",
        validation_plan="Interview platform teams and run a smoke-test pilot.",
        first_10_customers="agent framework maintainers; platform teams",
        domain_risks=["Framework adapters may change quickly"],
        evidence_rationale="Signals show repeated workflow safety gaps.",
        inspiring_insights=insight_ids,
        evidence_signals=signal_ids,
        tech_approach="Python service with YAML fixtures",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
        quality_score=8.0,
    )


def _seed_matrix_brief(tmp_path) -> tuple[Store, dict]:
    store = Store(str(tmp_path / "max.db"))
    signals = [
        _signal("sig-problem", "hackernews", "problem"),
        _signal("sig-market", "stackoverflow_survey", "market", source_type=SignalSourceType.SURVEY),
        _signal("sig-solution", "github_issues", "solution"),
        _signal("sig-risk", "nvd_cve", "risk", source_type=SignalSourceType.SECURITY),
    ]
    for signal in signals:
        store.insert_signal(signal)

    store.insert_insight(
        Insight(
            id="ins-gap",
            category=InsightCategory.GAP,
            title="Agent release safety gap",
            summary="Teams need repeatable release evidence for agent workflows.",
            evidence=["sig-problem", "sig-market"],
            confidence=0.85,
            domains=["developer-tools"],
        )
    )
    store.insert_insight(
        Insight(
            id="ins-risk",
            category=InsightCategory.VULNERABILITY,
            title="Workflow security risk",
            summary="Tool-using agents create workflow security exposure.",
            evidence=["sig-risk"],
            confidence=0.8,
            domains=["developer-tools"],
        )
    )

    lead = _unit(
        "bu-lead",
        insight_ids=["ins-gap"],
        signal_ids=["sig-problem", "sig-solution"],
        title="Agent Workflow Guard",
    )
    supporting = _unit(
        "bu-support",
        insight_ids=["ins-risk"],
        signal_ids=["sig-market", "sig-risk"],
        title="Agent Release Risk Monitor",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(supporting)

    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Agent Workflow Guard",
            domain="developer-tools",
            theme="agent-release-safety",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=supporting)],
            readiness_score=88.0,
            why_this_now="Agent tool use is entering production workflows.",
            merged_product_concept="A CI gate for agent workflow safety checks.",
            synthesis_rationale="Combines release safety pain with workflow risk monitoring.",
            mvp_scope=["Fixture runner", "Risk report"],
            first_milestones=["Run fixtures in CI", "Publish risk scorecards"],
            validation_plan="Interview platform teams and run a smoke-test pilot.",
            risks=["Framework churn could break adapters."],
            source_idea_ids=["bu-lead", "bu-support"],
        )
    )
    brief = store.get_design_brief(brief_id)
    assert brief is not None
    return store, brief


def test_build_design_brief_evidence_matrix_returns_claim_rows_from_persisted_data(tmp_path) -> None:
    store, brief = _seed_matrix_brief(tmp_path)
    try:
        matrix = build_design_brief_evidence_matrix(
            store,
            brief,
            generated_at="2026-04-24T00:00:00+00:00",
        )
    finally:
        store.close()

    assert matrix["schema_version"] == SCHEMA_VERSION
    assert matrix["source"]["id"] == brief["id"]
    assert matrix["design_brief"]["source_idea_ids"] == ["bu-lead", "bu-support"]
    assert [row["claim_area"] for row in matrix["rows"]] == list(CLAIM_AREAS)

    problem = next(row for row in matrix["rows"] if row["claim_area"] == "problem")
    assert problem["supporting_signal_ids"] == ["sig-problem"]
    assert problem["supporting_source_adapters"] == ["hackernews"]
    assert problem["supporting_insight_ids"] == ["ins-gap"]
    assert set(problem["supporting_source_idea_ids"]) == {"bu-lead", "bu-support"}
    assert problem["evidence_strength"] == "moderate"
    assert problem["validation_actions"]

    why_now = next(row for row in matrix["rows"] if row["claim_area"] == "why_now")
    assert why_now["supporting_signal_ids"] == ["sig-market"]
    assert why_now["supporting_source_adapters"] == ["stackoverflow_survey"]

    risks = next(row for row in matrix["rows"] if row["claim_area"] == "risks")
    assert risks["supporting_signal_ids"] == ["sig-risk"]
    assert risks["claim"] == "Framework churn could break adapters."


def test_build_design_brief_evidence_matrix_marks_missing_evidence_as_weak(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    unit = BuildableUnit(
        id="bu-thin",
        title="Thin Brief",
        one_liner="Thin evidence",
        category="application",
        problem="Problem",
        solution="Solution",
        value_proposition="Value",
        domain="testing",
        status="approved",
    )
    store.insert_buildable_unit(unit)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Thin Brief",
            domain="testing",
            theme="thin",
            lead=Candidate(unit=unit),
            readiness_score=50.0,
            why_this_now="",
            merged_product_concept="Solution",
            synthesis_rationale="",
            mvp_scope=[],
            first_milestones=[],
            validation_plan="",
            risks=[],
            source_idea_ids=["bu-thin"],
        )
    )
    brief = store.get_design_brief(brief_id)
    assert brief is not None
    try:
        matrix = build_design_brief_evidence_matrix(store, brief)
    finally:
        store.close()

    buyer = next(row for row in matrix["rows"] if row["claim_area"] == "buyer")
    assert buyer["evidence_strength"] == "weak"
    assert buyer["supporting_signal_ids"] == []
    assert "No persisted evidence signals are linked to this claim area." in buyer["gaps"]


def test_render_design_brief_evidence_matrix_json_markdown_and_invalid_format(tmp_path) -> None:
    store, brief = _seed_matrix_brief(tmp_path)
    try:
        matrix = build_design_brief_evidence_matrix(
            store,
            brief,
            generated_at="2026-04-24T00:00:00+00:00",
        )
    finally:
        store.close()

    parsed = json.loads(render_design_brief_evidence_matrix(matrix, fmt="json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    markdown = render_design_brief_evidence_matrix(matrix, fmt="markdown")
    assert markdown.startswith("# Evidence Matrix: Agent Workflow Guard")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    for claim_area in CLAIM_AREAS:
        assert f"## {claim_area}" in markdown
    assert "- **Evidence strength**: `moderate`" in markdown
    assert "- **Supporting signals**: `sig-problem`" in markdown
    assert "- **Supporting insights**: `ins-gap`" in markdown
    assert "- **Supporting source ideas**: `bu-lead`, `bu-support`" in markdown
    assert "### Gaps" in markdown
    assert "### Validation Actions" in markdown
    assert "- Run problem interviews with the primary user profile." in markdown

    with pytest.raises(ValueError, match="Unsupported evidence matrix format: yaml"):
        render_design_brief_evidence_matrix(matrix, fmt="yaml")


def test_render_design_brief_evidence_matrix_csv_has_stable_header(tmp_path) -> None:
    store, brief = _seed_matrix_brief(tmp_path)
    try:
        matrix = build_design_brief_evidence_matrix(store, brief)
    finally:
        store.close()

    rendered = render_design_brief_evidence_matrix(matrix, fmt="csv")

    assert rendered.startswith(CSV_HEADER)


def test_render_design_brief_evidence_matrix_csv_has_one_row_per_claim_evidence_link(
    tmp_path,
) -> None:
    store, brief = _seed_matrix_brief(tmp_path)
    try:
        matrix = build_design_brief_evidence_matrix(store, brief)
    finally:
        store.close()

    rows = list(csv.DictReader(StringIO(render_design_brief_evidence_matrix(matrix, fmt="csv"))))

    problem_rows = [row for row in rows if row["claim_id"] == "problem"]
    assert [row["evidence_id"] for row in problem_rows] == [
        "sig-problem",
        "ins-gap",
        "bu-lead",
        "bu-support",
    ]
    assert problem_rows[0]["source_type"] == "forum"
    assert problem_rows[0]["source_title"] == "Problem signal"
    assert problem_rows[0]["strength"] == "moderate"
    assert problem_rows[0]["confidence"] == "0.8"
    assert json.loads(problem_rows[0]["notes"]) == {
        "signal_role": "problem",
        "source_adapter": "hackernews",
        "tags": ["problem"],
    }
    assert any(row["claim_id"] == "risks" and row["evidence_id"] == "sig-risk" for row in rows)


def test_render_design_brief_evidence_matrix_csv_surfaces_contradictions() -> None:
    matrix = {
        "schema_version": SCHEMA_VERSION,
        "design_brief": {"id": "db-1", "title": "Brief"},
        "rows": [
            {
                "claim_area": "problem",
                "claim": "Teams need release evidence.",
                "evidence_strength": "weak",
                "supporting_evidence": [
                    {
                        "id": "sig-counter",
                        "source_type": "forum",
                        "source_title": "Counter signal",
                        "confidence": 0.7,
                        "contradiction_flag": True,
                        "notes": ["mentions successful manual reviews"],
                    }
                ],
            }
        ],
    }

    rows = list(csv.DictReader(StringIO(render_design_brief_evidence_matrix(matrix, fmt="csv"))))

    assert rows[0]["contradiction_flag"] == "True"
    assert rows[0]["evidence_id"] == "sig-counter"
    assert rows[0]["notes"] == '["mentions successful manual reviews"]'


def test_render_design_brief_evidence_matrix_csv_empty_matrix_is_header_only() -> None:
    matrix = {
        "schema_version": SCHEMA_VERSION,
        "design_brief": {"id": "db-empty", "title": "Empty Brief"},
        "rows": [],
    }

    assert render_design_brief_evidence_matrix(matrix, fmt="csv") == CSV_HEADER

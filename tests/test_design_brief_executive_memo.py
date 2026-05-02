"""Tests for design brief executive memo exports."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_executive_memo import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_executive_memo,
    render_design_brief_executive_memo,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


def _signal(signal_id: str, source_type: SignalSourceType, role: str) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=f"test-{source_type.value}",
        title=f"{role.title()} memo evidence",
        content=f"Evidence supporting executive memo {role}.",
        url=f"https://example.com/{signal_id}",
        tags=[role],
        credibility=0.8,
        metadata={"signal_role": role},
    )


def _unit(unit_id: str, signal_ids: list[str]) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="Executive Memo Lead",
        one_liner="Approval memo for design brief handoff",
        category="application",
        problem="Decision-makers need a compact approval artifact.",
        solution="Summarize brief evidence, risks, and validation next step.",
        value_proposition="Reduce review time for persisted design briefs.",
        specific_user="product decision-maker",
        buyer="VP product",
        workflow_context="design brief approval review",
        current_workaround="manual summary notes",
        why_now="Design brief bundles are already persisted.",
        validation_plan="Run the memo through an owner approval review.",
        first_10_customers="product leadership teams",
        domain_risks=["Owner alignment may be unclear."],
        evidence_rationale="Signals show handoff review friction.",
        evidence_signals=signal_ids,
        tech_approach="Deterministic FastAPI export.",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
    )


def _evaluation(unit_id: str) -> UtilityEvaluation:
    dim = DimensionScore(value=8.0, confidence=0.8, reasoning="test")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=dim,
        timing_fit=dim,
        compounding_value=dim,
        overall_score=82.0,
        recommendation="yes",
    )


def _seed_design_brief(store: Store) -> str:
    for signal in [
        _signal("sig-memo-forum", SignalSourceType.FORUM, "problem"),
        _signal("sig-memo-survey", SignalSourceType.SURVEY, "market"),
        _signal("sig-memo-funding", SignalSourceType.FUNDING, "market"),
    ]:
        store.insert_signal(signal)
    lead = _unit("bu-memo-lead", ["sig-memo-forum", "sig-memo-survey", "sig-memo-funding"])
    store.insert_buildable_unit(lead)
    store.insert_evaluation(_evaluation(lead.id))
    return store.insert_design_brief(
        ProjectBrief(
            title="Executive Memo Brief",
            domain="developer-tools",
            theme="approval-handoff",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=86.0,
            why_this_now="Decision-makers need one approval-ready artifact.",
            merged_product_concept="A deterministic executive memo export.",
            synthesis_rationale="Combines brief content with evidence, risk, and market artifacts.",
            mvp_scope=["Executive memo JSON", "Executive memo Markdown"],
            first_milestones=["Build memo composer", "Expose API export"],
            validation_plan="Review the memo with the owner before implementation.",
            risks=["Owner alignment may be unclear."],
            source_idea_ids=[lead.id],
        )
    )


def test_build_design_brief_executive_memo_is_deterministic_for_persisted_brief(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "executive_memo.db"), wal_mode=True)
    try:
        brief_id = _seed_design_brief(store)
        memo = build_design_brief_executive_memo(store, brief_id)
        repeated = build_design_brief_executive_memo(store, brief_id)
    finally:
        store.close()

    assert memo == repeated
    assert memo is not None
    assert memo["schema_version"] == SCHEMA_VERSION
    assert memo["design_brief"]["id"] == brief_id
    assert memo["decision_summary"]["recommendation"] == "approve-validation"
    assert memo["target_segment"]["buyer"] == "VP product"
    assert memo["problem"] == "Decision-makers need a compact approval artifact."
    assert "executive memo export" in memo["proposed_product"]
    assert memo["evidence_highlights"]
    assert memo["market_size_confidence"]["level"] in {"medium", "high"}
    assert memo["top_risks"][0]["title"] == "Owner alignment may be unclear"
    assert memo["decisions_needed"]
    assert [milestone["title"] for milestone in memo["milestones"]] == [
        "Build memo composer",
        "Expose API export",
    ]
    assert memo["next_actions"][0]["title"] == "Validation next step"
    assert memo["validation_next_step"]["action"]
    assert memo["owner_ask"].startswith("Assign an owner")


def test_render_design_brief_executive_memo_json_markdown_and_invalid_format(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "executive_memo_render.db"), wal_mode=True)
    try:
        brief_id = _seed_design_brief(store)
        memo = build_design_brief_executive_memo(store, brief_id)
    finally:
        store.close()

    assert memo is not None
    parsed = json.loads(render_design_brief_executive_memo(memo, fmt="json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    markdown = render_design_brief_executive_memo(memo, fmt="markdown")
    assert markdown.startswith("# Executive Memo: Executive Memo Brief")
    assert "## Decision Summary" in markdown
    assert "## Evidence Highlights" in markdown
    assert "## Risks" in markdown
    assert "## Validation Next Step" in markdown
    assert "Owner alignment may be unclear" in markdown

    with pytest.raises(ValueError):
        render_design_brief_executive_memo(memo, fmt="yaml")


def test_render_design_brief_executive_memo_csv_headers_rows_and_nested_cells(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "executive_memo_csv.db"), wal_mode=True)
    try:
        brief_id = _seed_design_brief(store)
        memo = build_design_brief_executive_memo(store, brief_id)
    finally:
        store.close()

    assert memo is not None
    csv_text = render_design_brief_executive_memo(memo, fmt="csv")
    repeated = render_design_brief_executive_memo(memo, fmt="csv")
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)

    assert csv_text == repeated
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)

    sections = {row["section"] for row in rows}
    assert {
        "summary",
        "evidence",
        "risks",
        "decisions_needed",
        "milestones",
        "next_actions",
    } <= sections

    summary = rows[0]
    assert summary["design_brief_id"] == brief_id
    assert summary["design_brief_title"] == "Executive Memo Brief"
    assert summary["section"] == "summary"
    assert summary["item_id"] == "recommendation"
    assert summary["recommendation"] == "approve-validation"
    assert json.loads(summary["source_idea_ids"]) == ["bu-memo-lead"]

    evidence = next(row for row in rows if row["section"] == "evidence")
    evidence_detail = json.loads(evidence["detail"])
    assert evidence["priority"] in {"strong", "moderate", "weak"}
    assert "claim" in evidence_detail
    assert set(evidence_detail["supporting_signal_ids"]) <= {
        "sig-memo-forum",
        "sig-memo-funding",
        "sig-memo-survey",
    }
    assert evidence_detail["supporting_signal_ids"]
    assert json.loads(evidence["source_idea_ids"]) == ["bu-memo-lead"]

    risk = next(row for row in rows if row["section"] == "risks")
    risk_detail = json.loads(risk["detail"])
    assert risk["item_title"] == "Owner alignment may be unclear"
    assert risk["severity"]
    assert risk["priority"]
    assert risk_detail["validation_action"]

    decision = next(
        row for row in rows if row["section"] == "decisions_needed" and row["item_id"] == "DEC1"
    )
    assert decision["owner"] == "business owner"
    assert decision["recommendation"] == "approve-validation"

    milestone = next(
        row for row in rows if row["section"] == "milestones" and row["item_id"] == "M1"
    )
    assert milestone["item_title"] == "Build memo composer"
    assert milestone["recommendation"] == "track"

    action = next(
        row for row in rows if row["section"] == "next_actions" and row["item_id"] == "ACT1"
    )
    assert action["owner"] == "assigned owner"
    assert action["detail"]

    with pytest.raises(ValueError):
        render_design_brief_executive_memo(memo, fmt="yaml")


def test_build_design_brief_executive_memo_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "executive_memo_missing.db"), wal_mode=True)
    try:
        assert build_design_brief_executive_memo(store, "dbf-missing") is None
    finally:
        store.close()

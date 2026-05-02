"""Tests for design brief competitive alternatives matrices."""

from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis import (
    build_design_brief_competitive_alternatives as exported_build_competitive_alternatives,
)
from max.analysis.design_brief_competitive_alternatives import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_buildable_unit_competitive_alternatives,
    build_design_brief_competitive_alternatives,
    competitive_alternatives_filename,
    render_design_brief_competitive_alternatives,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_competitive_alternatives_uses_prior_art_and_structured_context(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        report = build_design_brief_competitive_alternatives(store, brief_id)
        repeated = build_design_brief_competitive_alternatives(store, brief_id)
    finally:
        store.close()

    assert report == repeated
    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"]["status"] == "ready"
    assert report["summary"]["target_user"] == "sales operations manager"
    assert report["summary"]["buyer"] == "VP of Revenue Operations"
    assert report["summary"]["workflow_context"] == "renewal risk review"
    assert report["summary"]["direct_competitor_count"] == 2
    assert report["summary"]["indirect_alternative_count"] == 3
    assert [entry["type"] for entry in report["competitor_entries"]] == [
        "direct_competitor",
        "direct_competitor",
        "indirect_alternative",
        "indirect_alternative",
        "indirect_alternative",
    ]
    assert report["direct_competitors"][0]["name"] == "RenewalAI Watchtower"
    assert report["direct_competitors"][0]["substitution_risk"] == "high"
    assert report["workaround_entries"][0]["behavior"] == "manual spreadsheets and Slack deal reviews"
    assert report["differentiator_entries"][0]["claim"] == "Built for sales operations manager"
    assert report["evidence_gap_entries"][-1]["gap"] == "Differentiator proof is not yet decisive"
    assert len(report["matrix_rows"]) >= 6
    assert json.loads(json.dumps(report))["kind"] == KIND
    assert exported_build_competitive_alternatives is build_design_brief_competitive_alternatives


def test_competitive_alternatives_sparse_brief_returns_fallback_rows(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store, sparse=True, with_prior_art=False)
        report = build_design_brief_competitive_alternatives(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["status"] == "fallbacks_used"
    assert report["summary"]["fallbacks_used"] == [
        "target_user",
        "buyer",
        "workflow_context",
        "value_proposition",
        "current_workaround",
    ]
    assert report["direct_competitors"][0]["id"] == "DC0"
    assert report["direct_competitors"][0]["name"] == "Unverified direct competitor"
    assert report["workaround_entries"][0]["id"] == "WA1"
    assert report["indirect_alternatives"][0]["name"] == "Status quo workflow"
    assert [gap["gap"] for gap in report["evidence_gap_entries"]][:3] == [
        "No stored prior-art matches",
        "Current workaround is inferred",
        "Persona or buyer evidence is sparse",
    ]
    assert report["matrix_rows"]


def test_render_competitive_alternatives_markdown_json_and_invalid_format(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        report = build_design_brief_competitive_alternatives(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_competitive_alternatives(report)
    assert markdown.startswith("# Competitive Alternatives Matrix: Renewal Risk Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Kind: `{KIND}`" in markdown
    assert "## Alternatives Matrix" in markdown
    assert "## Direct Competitors" in markdown
    assert "## Indirect Alternatives" in markdown
    assert "## Current Workarounds" in markdown
    assert "## Differentiators" in markdown
    assert "## Evidence Gaps" in markdown
    assert "| Type | Alternative | Substitution risk | Switching friction | Differentiation response | Evidence |" in markdown

    parsed = json.loads(render_design_brief_competitive_alternatives(report, fmt="json"))
    assert parsed == report

    with pytest.raises(ValueError, match="Unsupported competitive alternatives format: yaml"):
        render_design_brief_competitive_alternatives(report, fmt="yaml")


def test_render_competitive_alternatives_csv_headers_order_and_escaping(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        report = build_design_brief_competitive_alternatives(store, brief_id)
    finally:
        store.close()

    assert report is not None
    report["matrix_rows"][0]["alternative"] = 'RenewalAI, "Watchtower"\nEnterprise'
    report["matrix_rows"][0]["differentiation_response"] = (
        'Lead with buyer proof, "workflow" fit,\nand governance readiness.'
    )
    report["matrix_rows"][0]["evidence"] = 'pa-1, "bu-renewal-lead"'

    csv_text = render_design_brief_competitive_alternatives(report, fmt="csv")
    repeated = render_design_brief_competitive_alternatives(report, fmt="csv")
    reader = csv.DictReader(StringIO(csv_text))
    rows = list(reader)

    assert csv_text == repeated
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert len(rows) == len(report["matrix_rows"])
    assert [row["competitor_alternative_name"] for row in rows[:3]] == [
        'RenewalAI, "Watchtower"\nEnterprise',
        "renewal-health-scorecard",
        "Status quo workflow",
    ]
    assert rows[0]["target_segment"] == "sales operations manager"
    assert rows[0]["differentiators"] == (
        'Lead with buyer proof, "workflow" fit,\nand governance readiness.'
    )
    assert rows[0]["weaknesses"].startswith("Substitution risk: high; Switching friction:")
    assert rows[0]["evidence_references"] == 'pa-1, "bu-renewal-lead"'
    assert rows[0]["recommended_positioning"].startswith(
        'Position for sales operations manager against RenewalAI, "Watchtower"\nEnterprise:'
    )
    assert '"RenewalAI, ""Watchtower""\nEnterprise"' in csv_text
    assert '"Lead with buyer proof, ""workflow"" fit,\nand governance readiness."' in csv_text
    assert '"pa-1, ""bu-renewal-lead"""' in csv_text


def test_render_competitive_alternatives_csv_empty_matrix_exports_header_only(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        report = build_design_brief_competitive_alternatives(store, brief_id)
    finally:
        store.close()

    assert report is not None
    report["matrix_rows"] = []

    csv_text = render_design_brief_competitive_alternatives(report, fmt="csv")
    reader = csv.DictReader(StringIO(csv_text))

    assert reader.fieldnames == list(CSV_COLUMNS)
    assert list(reader) == []
    assert csv_text == ",".join(CSV_COLUMNS) + "\n"


def test_buildable_unit_competitive_alternatives_entry_point(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        unit = _unit("bu-standalone", sparse=False)
        store.insert_buildable_unit(unit)
        store.insert_prior_art_match(
            unit.id,
            {
                "source": "github",
                "title": "renewal-risk-open",
                "url": "https://github.com/example/renewal-risk-open",
                "description": "Open-source renewal risk review workflow.",
                "relevance_score": 0.72,
                "match_signals": {"stars": 42},
                "search_query": "renewal risk review",
            },
        )
        report = build_buildable_unit_competitive_alternatives(store, unit.id)
    finally:
        store.close()

    assert report is not None
    assert report["source"]["entity_type"] == "buildable_unit"
    assert report["design_brief"]["id"] == "bu-standalone"
    assert report["summary"]["status"] == "ready"
    assert report["direct_competitors"][0]["name"] == "renewal-risk-open"


def test_competitive_alternatives_missing_entities_return_none(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        assert build_design_brief_competitive_alternatives(store, "dbf-missing") is None
        assert build_buildable_unit_competitive_alternatives(store, "bu-missing") is None
    finally:
        store.close()


def test_competitive_alternatives_filename_uses_brief_id() -> None:
    brief = {"id": "dbf-test001", "title": "Ignored Title"}
    assert (
        competitive_alternatives_filename(brief, fmt="markdown")
        == "dbf-test001-competitive-alternatives.md"
    )
    assert (
        competitive_alternatives_filename(brief, fmt="json")
        == "dbf-test001-competitive-alternatives.json"
    )
    assert (
        competitive_alternatives_filename(brief, fmt="csv")
        == "dbf-test001-competitive-alternatives.csv"
    )


def _seed_brief(
    store: Store,
    *,
    sparse: bool = False,
    with_prior_art: bool = True,
) -> str:
    lead = _unit("bu-renewal-lead", sparse=sparse)
    support = _unit("bu-renewal-support", sparse=sparse)
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(support)

    if with_prior_art:
        store.insert_prior_art_match(
            lead.id,
            {
                "source": "product_hunt",
                "title": "RenewalAI Watchtower",
                "url": "https://www.producthunt.com/products/renewalai-watchtower",
                "description": "AI renewal risk review and expansion workflow for revenue teams.",
                "relevance_score": 0.91,
                "match_signals": {"votes": 180},
                "search_query": "renewal risk review",
            },
        )
        store.insert_prior_art_match(
            support.id,
            {
                "source": "github",
                "title": "renewal-health-scorecard",
                "url": "https://github.com/example/renewal-health-scorecard",
                "description": "Open-source scorecard for renewal health reviews.",
                "relevance_score": 0.68,
                "match_signals": {"stars": 86},
                "search_query": "renewal health scorecard",
            },
        )

    return store.insert_design_brief(
        ProjectBrief(
            title="Renewal Risk Brief",
            domain="sales",
            theme="renewal-risk",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=82.0 if not sparse else 24.0,
            why_this_now=(
                "Revenue teams face procurement and security review pressure before renewals."
                if not sparse
                else ""
            ),
            merged_product_concept=(
                "A focused renewal risk matrix for revenue operations teams."
                if not sparse
                else ""
            ),
            synthesis_rationale=(
                "Combines risk scoring, account evidence, and renewal review handoff."
                if not sparse
                else ""
            ),
            mvp_scope=["Renewal risk scorecard", "Buyer-ready account recap"] if not sparse else [],
            first_milestones=["Export competitive alternatives matrix"] if not sparse else [],
            validation_plan="Run five buyer interviews against current renewal review behavior."
            if not sparse
            else "",
            risks=["Security review and procurement approval may slow switching."] if not sparse else [],
            source_idea_ids=[lead.id, support.id],
            design_status="approved" if not sparse else "draft",
        )
    )


def _unit(unit_id: str, *, sparse: bool) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="Renewal Risk Matrix" if not sparse else "Sparse Competitive Lead",
        one_liner="Compare renewal alternatives before spec generation.",
        category="application",
        problem=(
            "Revenue teams cannot compare renewal risk alternatives before account reviews."
            if not sparse
            else ""
        ),
        solution=(
            "Generate a renewal risk matrix with competitors, workarounds, and proof gaps."
            if not sparse
            else ""
        ),
        value_proposition=(
            "Reduce renewal surprise by comparing alternatives and proof gaps before handoff."
            if not sparse
            else ""
        ),
        specific_user="sales operations manager" if not sparse else "",
        buyer="VP of Revenue Operations" if not sparse else "",
        workflow_context="renewal risk review" if not sparse else "",
        current_workaround="manual spreadsheets and Slack deal reviews" if not sparse else "",
        why_now="Renewal teams need sharper evidence before procurement cycles." if not sparse else "",
        validation_plan="Interview revenue operations managers and compare current workaround behavior."
        if not sparse
        else "",
        first_10_customers="B2B SaaS revenue teams managing renewals" if not sparse else "",
        domain_risks=["Procurement approval may slow switching."] if not sparse else [],
        evidence_rationale="Discovery suggests spreadsheets hide renewal risks." if not sparse else "",
        evidence_signals=["sig-renewal-risk"] if not sparse else [],
        inspiring_insights=["ins-renewal-workaround"] if not sparse else [],
        tech_approach="Deterministic Python report export." if not sparse else "",
        suggested_stack={"backend": "FastAPI", "storage": "SQLite"} if not sparse else {},
        domain="sales" if not sparse else "",
        status="approved" if not sparse else "draft",
    )

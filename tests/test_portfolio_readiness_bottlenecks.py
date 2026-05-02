"""Tests for portfolio readiness bottleneck reporting."""

from __future__ import annotations

import csv
import json
from io import StringIO

import pytest
from max.analysis import build_portfolio_readiness_bottlenecks as exported_build
from max.analysis import render_portfolio_readiness_bottlenecks as exported_render
from max.analysis.portfolio_readiness_bottlenecks import (
    SCHEMA_VERSION,
    build_portfolio_readiness_bottlenecks,
    render_portfolio_readiness_bottlenecks,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def test_readiness_bottlenecks_groups_mixed_blockers(store: Store) -> None:
    uncertain = _unit(
        "bu-uncertain",
        "Patient Intake Reviewer",
        status="evaluated",
        quality=4.4,
        evidence=[],
        validation_plan="TBD",
        tech="Unknown HIPAA integration risk with Python and PostgreSQL.",
        stack={"language": "python", "database": "postgres"},
        buyer="hospital compliance buyer",
        specific_user="nurse manager",
        target_users="patient intake teams",
        domain_risks=["HIPAA privacy and security review required."],
    )
    shared = _unit(
        "bu-shared",
        "Invoice Audit Queue",
        status="approved",
        quality=7.8,
        evidence=["sig-invoice"],
        validation_plan="Run a pilot test with five finance operators and measure review time.",
        tech="Python service backed by PostgreSQL.",
        stack={"language": "python", "database": "postgres"},
        buyer="finance operations leader",
        specific_user="accounts payable analyst",
        target_users="finance operators",
        domain_risks=["SOX audit evidence may be required."],
    )
    vague = _unit(
        "bu-vague",
        "Workflow Helper",
        status="approved",
        quality=8.1,
        evidence=["sig-vague"],
        validation_plan="Interview five operations leads and measure task completion.",
        tech="React console for workflow review.",
        stack={"frontend": "react"},
        buyer="",
        specific_user="",
        target_users="users",
    )
    for unit in (uncertain, shared, vague):
        store.insert_buildable_unit(unit)

    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Shared Audit Brief",
            domain="finops",
            theme="audit",
            lead=Candidate(unit=shared),
            readiness_score=62.0,
            why_this_now="Audit operations need clearer execution readiness.",
            merged_product_concept="A Python and PostgreSQL workflow for invoice audit review.",
            synthesis_rationale="Source evidence points to audit queue demand.",
            mvp_scope=["Python service", "PostgreSQL audit log"],
            first_milestones=["Prototype the audit queue"],
            validation_plan="Pilot test with finance operators and measure cycle time.",
            risks=["Procurement and SOX compliance may delay rollout."],
            source_idea_ids=[shared.id],
            design_status="candidate",
        )
    )

    report = build_portfolio_readiness_bottlenecks(store)

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.portfolio_readiness_bottlenecks"
    assert report["summary"]["total_items"] == 4
    assert report["summary"]["low_readiness_item_count"] == 2

    buckets = {bucket["category"]: bucket for bucket in report["bottlenecks"]}
    assert set(buckets) >= {
        "evidence_gaps",
        "validation_gaps",
        "technical_uncertainty",
        "compliance_risk",
        "dependency_concentration",
        "customer_acquisition_ambiguity",
        "low_readiness_score",
    }
    assert buckets["low_readiness_score"]["affected_item_ids"] == ["bu-uncertain", brief_id]
    assert buckets["evidence_gaps"]["representative_ids"] == ["bu-uncertain"]
    assert "PostgreSQL" in {
        field.get("dependency")
        for field in buckets["dependency_concentration"]["evidence_fields"]
    }
    assert buckets["dependency_concentration"]["count"] == 3
    assert buckets["compliance_risk"]["severity"] == "high"
    assert json.loads(json.dumps(report))["summary"]["total_items"] == 4


def test_readiness_bottlenecks_status_filter_and_exports(store: Store) -> None:
    store.insert_buildable_unit(
        _unit(
            "bu-approved",
            "Approved Ready",
            status="approved",
            quality=8.2,
            evidence=["sig-approved"],
            validation_plan="Pilot test with three teams and measure activation.",
            tech="React UI.",
            stack={"frontend": "react"},
            buyer="platform leader",
            specific_user="release manager",
        )
    )
    store.insert_buildable_unit(
        _unit(
            "bu-draft",
            "Draft Sparse",
            status="draft",
            quality=3.2,
            evidence=[],
            validation_plan="",
            tech="",
            stack={},
            buyer="",
            specific_user="",
        )
    )

    report = exported_build(store, status="approved")

    assert report["filters"] == {"status": "approved"}
    assert report["summary"]["total_items"] == 1
    assert report["summary"]["low_readiness_item_count"] == 0
    assert "bu-draft" not in {
        item_id
        for bucket in report["bottlenecks"]
        for item_id in bucket["affected_item_ids"]
    }
    assert exported_render(report) == render_portfolio_readiness_bottlenecks(report)


def test_readiness_bottlenecks_csv_renderer_includes_stable_check_rows(
    store: Store,
) -> None:
    for unit in [
        _unit(
            "bu-a",
            "A",
            status="approved",
            quality=8.1,
            evidence=[],
            validation_plan="",
            tech="React UI.",
            stack={"frontend": "react"},
            buyer="platform leader",
            specific_user="release manager",
        ),
        _unit(
            "bu-b",
            "B",
            status="approved",
            quality=8.2,
            evidence=[],
            validation_plan="",
            tech="React UI.",
            stack={"frontend": "react"},
            buyer="platform leader",
            specific_user="release manager",
        ),
    ]:
        store.insert_buildable_unit(unit)

    report = build_portfolio_readiness_bottlenecks(store)

    csv_text = render_portfolio_readiness_bottlenecks(report, fmt="csv")
    assert csv_text.startswith(
        "bottleneck_id,check_id,category,title,severity,affected_count,"
        "portfolio_share,affected_idea_ids,failed_check_ids,recommendation,owner,action\n"
    )
    assert csv_text == render_portfolio_readiness_bottlenecks(report, fmt="csv")
    rows = list(csv.DictReader(StringIO(csv_text)))

    evidence_row = next(
        row
        for row in rows
        if row["bottleneck_id"] == "readiness:evidence_gaps"
        and row["check_id"] == "readiness_evidence_gaps:evidence_ids"
    )
    assert evidence_row["severity"] == "high"
    assert evidence_row["affected_count"] == "2"
    assert evidence_row["affected_idea_ids"] == "bu-a;bu-b"
    assert evidence_row["failed_check_ids"] == (
        "readiness_evidence_gaps:evidence_ids;"
        "readiness_evidence_gaps:evidence_rationale"
    )
    assert "Attach source evidence" in evidence_row["recommendation"]
    assert evidence_row["action"] == evidence_row["recommendation"]


def test_readiness_bottlenecks_sparse_portfolio_is_low_confidence(store: Store) -> None:
    store.insert_buildable_unit(
        _unit(
            "bu-sparse",
            "Sparse Note Tool",
            status="approved",
            quality=8.0,
            evidence=["sig-sparse"],
            validation_plan="Interview three note takers and measure adoption intent.",
            tech="React UI.",
            stack={"frontend": "react"},
            buyer="productivity leader",
            specific_user="research operations lead",
        )
    )

    report = build_portfolio_readiness_bottlenecks(store)
    markdown = render_portfolio_readiness_bottlenecks(report)

    assert report["summary"]["total_items"] == 1
    assert report["summary"]["confidence"] == "low"
    assert report["bottlenecks"] == []
    assert "No reportable readiness bottlenecks were detected." in markdown


def test_readiness_bottlenecks_empty_and_markdown_json(store: Store) -> None:
    report = build_portfolio_readiness_bottlenecks(store, status="approved")
    markdown = render_portfolio_readiness_bottlenecks(report)
    rendered_json = render_portfolio_readiness_bottlenecks(report, fmt="json")

    assert report["summary"]["total_items"] == 0
    assert report["summary"]["confidence"] == "low"
    assert "Items analyzed: 0" in markdown
    assert "No portfolio items matched the selected filters." in markdown
    assert json.loads(rendered_json)["kind"] == "max.portfolio_readiness_bottlenecks"


def test_readiness_bottlenecks_empty_csv_returns_header(store: Store) -> None:
    report = build_portfolio_readiness_bottlenecks(store, status="approved")

    csv_text = render_portfolio_readiness_bottlenecks(report, fmt="csv")

    assert list(csv.DictReader(StringIO(csv_text))) == []
    assert csv_text == (
        "bottleneck_id,check_id,category,title,severity,affected_count,"
        "portfolio_share,affected_idea_ids,failed_check_ids,recommendation,owner,action\n"
    )


def test_readiness_bottlenecks_renderer_rejects_unsupported_format(store: Store) -> None:
    report = build_portfolio_readiness_bottlenecks(store)

    with pytest.raises(ValueError, match="Unsupported portfolio readiness bottlenecks format"):
        render_portfolio_readiness_bottlenecks(report, fmt="xml")


def test_readiness_bottlenecks_sorting_is_deterministic(store: Store) -> None:
    for unit in [
        _unit(
            "bu-c",
            "C",
            status="evaluated",
            quality=4.1,
            evidence=[],
            validation_plan="",
            tech="Unknown Python feasibility.",
            stack={"language": "python"},
            buyer="",
            specific_user="",
        ),
        _unit(
            "bu-a",
            "A",
            status="evaluated",
            quality=4.2,
            evidence=[],
            validation_plan="",
            tech="Unknown Python feasibility.",
            stack={"language": "python"},
            buyer="",
            specific_user="",
        ),
        _unit(
            "bu-b",
            "B",
            status="evaluated",
            quality=4.3,
            evidence=[],
            validation_plan="",
            tech="Unknown Python feasibility.",
            stack={"language": "python"},
            buyer="",
            specific_user="",
        ),
    ]:
        store.insert_buildable_unit(unit)

    first = build_portfolio_readiness_bottlenecks(store)
    second = build_portfolio_readiness_bottlenecks(store)

    assert first["bottlenecks"] == second["bottlenecks"]
    assert first["bottlenecks"][0]["severity"] == "high"
    assert _bucket(first, "evidence_gaps")["affected_item_ids"] == ["bu-a", "bu-b", "bu-c"]
    assert render_portfolio_readiness_bottlenecks(first).startswith(
        "# Portfolio Readiness Bottlenecks\n"
    )


def _bucket(report: dict, category: str) -> dict:
    return next(bucket for bucket in report["bottlenecks"] if bucket["category"] == category)


def _unit(
    unit_id: str,
    title: str,
    *,
    status: str,
    quality: float,
    evidence: list[str],
    validation_plan: str,
    tech: str,
    stack: dict,
    buyer: str,
    specific_user: str,
    target_users: str = "operations teams",
    domain_risks: list[str] | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner=f"{title} for portfolio readiness reviews.",
        category=BuildableCategory.APPLICATION,
        problem="Operators cannot identify execution-readiness blockers.",
        solution=tech or "Clarify readiness blockers.",
        target_users=target_users,
        value_proposition="Focus execution planning on blockers.",
        specific_user=specific_user,
        buyer=buyer,
        workflow_context="portfolio review",
        validation_plan=validation_plan,
        evidence_signals=evidence,
        inspiring_insights=[],
        quality_score=quality,
        usefulness_score=quality,
        status=status,
        domain="finops",
        domain_risks=domain_risks or [],
        tech_approach=tech,
        suggested_stack=stack,
    )

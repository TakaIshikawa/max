"""Tests for portfolio cannibalization analysis."""

from __future__ import annotations

import json

import pytest

from max.analysis.portfolio_cannibalization import (
    SCHEMA_VERSION,
    build_portfolio_cannibalization_from_records,
    build_portfolio_cannibalization_report,
    render_portfolio_cannibalization_report,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def test_cannibalization_does_not_flag_unrelated_items_above_default_threshold(
    store: Store,
) -> None:
    store.insert_buildable_unit(
        _unit(
            "bu-payroll",
            "Payroll Export Cleaner",
            buyer="finance operations director",
            specific_user="payroll analyst",
            workflow="payroll spreadsheet close",
            problem="Payroll teams fix malformed spreadsheet exports before monthly close.",
            solution="Normalize payroll CSV exports with field validation and exception review.",
            domain="finops",
            category=BuildableCategory.AUTOMATION,
            stack={"language": "python", "surface": "cli"},
        )
    )
    store.insert_buildable_unit(
        _unit(
            "bu-security",
            "MCP Threat Model Reviewer",
            buyer="security engineering manager",
            specific_user="appsec engineer",
            workflow="protocol security review",
            problem="Security teams miss threat model gaps in MCP server releases.",
            solution="Review protocol manifests and produce threat model findings.",
            domain="security",
            category=BuildableCategory.APPLICATION,
            stack={"language": "typescript", "surface": "web"},
        )
    )

    report = build_portfolio_cannibalization_report(store)

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.portfolio_cannibalization"
    assert report["summary"]["total_items"] == 2
    assert report["summary"]["flagged_pair_count"] == 0
    assert report["analyzed_idea_ids"] == ["bu-payroll", "bu-security"]
    assert report["pair_findings"] == []
    assert "no item pair crossed" in report["recommendations"][0]["action"]


def test_cannibalization_flags_high_buyer_and_workflow_overlap(store: Store) -> None:
    store.insert_buildable_unit(
        _unit(
            "bu-runbook",
            "Incident Runbook Drafter",
            buyer="platform engineering director",
            specific_user="sre lead",
            workflow="incident response handoff",
            problem="SRE leads lose context when incident notes become follow up tasks.",
            solution="Draft runbooks and owners from incident notes.",
            evidence=["sig-incident-1"],
        )
    )
    store.insert_buildable_unit(
        _unit(
            "bu-retro",
            "Incident Retro Planner",
            buyer="platform engineering director",
            specific_user="sre lead",
            workflow="incident response handoff",
            problem="SRE leads struggle to turn incident notes into retro agendas.",
            solution="Create retrospectives, agenda items, and follow up owner lists.",
            evidence=["sig-incident-2"],
        )
    )

    report = build_portfolio_cannibalization_report(store)

    assert report["summary"]["flagged_pair_count"] == 1
    finding = report["pair_findings"][0]
    assert finding["ids"] == ["bu-retro", "bu-runbook"]
    assert finding["severity"] in {"low", "medium", "high"}
    assert finding["score_components"]["buyer"] >= 0.5
    assert finding["score_components"]["workflow"] >= 0.5
    assert {reason["type"] for reason in finding["reasons"]} >= {"buyer", "workflow"}
    assert any("narrower buyer" in action for action in finding["differentiation_actions"])
    assert report["clusters"][0]["ids"] == ["bu-retro", "bu-runbook"]


def test_cannibalization_flags_high_solution_overlap_between_brief_and_idea(
    store: Store,
) -> None:
    lead = _unit(
        "bu-protocol-gate",
        "Protocol Release Gate",
        buyer="developer platform lead",
        specific_user="sdk maintainer",
        workflow="sdk release readiness",
        problem="SDK maintainers miss release blockers before publishing packages.",
        solution="Scan release checklists and block package publication on missing evidence.",
        evidence=["sig-release-gate"],
        stack={"language": "typescript", "surface": "github-action", "runtime": "node"},
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(
        _unit(
            "bu-package-gate",
            "Package Publication Gate",
            buyer="developer experience manager",
            specific_user="package maintainer",
            workflow="package release readiness",
            problem="Package maintainers ship releases without required checks.",
            solution="Block package publication with a GitHub Action release gate and checklist evidence.",
            evidence=["sig-package-gate"],
            stack={"language": "typescript", "surface": "github-action", "runtime": "node"},
        )
    )
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Release Gate Brief",
            domain="devtools",
            theme="release",
            lead=Candidate(unit=lead),
            readiness_score=86.0,
            why_this_now="Release governance needs a lightweight gate.",
            merged_product_concept=(
                "A GitHub Action release gate that blocks package publication until checklist "
                "evidence is complete."
            ),
            synthesis_rationale="The source idea focuses on release readiness gates.",
            mvp_scope=["GitHub Action release gate", "checklist evidence blocking"],
            first_milestones=["Ship release gate workflow"],
            validation_plan="Test with two SDK teams.",
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )

    report = build_portfolio_cannibalization_report(store)

    brief_pair = next(
        pair
        for pair in report["pair_findings"]
        if set(pair["ids"]) == {brief_id, "bu-package-gate"}
    )
    assert brief_pair["score"] >= 0.45
    assert brief_pair["score_components"]["solution"] >= 0.35
    assert brief_pair["score_components"]["implementation_scope"] >= 0.35
    assert {reason["type"] for reason in brief_pair["reasons"]} >= {
        "solution",
        "implementation_scope",
    }
    assert any("delivery surface" in action for action in brief_pair["differentiation_actions"])
    assert any("generated idea and design brief" in action for action in brief_pair["differentiation_actions"])


def test_cannibalization_ordering_is_stable_for_equal_scores_and_sparse_metadata() -> None:
    units = [
        _unit(
            "bu-c",
            "Shared Scope C",
            buyer="ops director",
            specific_user="ops analyst",
            workflow="weekly review",
            problem="Ops teams review queues weekly.",
            solution="Show queue review dashboards.",
        ),
        _unit(
            "bu-a",
            "Shared Scope A",
            buyer="ops director",
            specific_user="ops analyst",
            workflow="weekly review",
            problem="Ops teams review queues weekly.",
            solution="Show queue review dashboards.",
        ),
        _unit(
            "bu-b",
            "Shared Scope B",
            buyer="ops director",
            specific_user="ops analyst",
            workflow="weekly review",
            problem="Ops teams review queues weekly.",
            solution="Show queue review dashboards.",
        ),
    ]

    report = build_portfolio_cannibalization_from_records(
        buildable_units=units,
        design_briefs=[
            {
                "id": "dbf-a",
                "title": "Sparse Shared Brief",
                "domain": "ops",
                "theme": "review",
                "readiness_score": 0.0,
                "buyer": "",
                "specific_user": "",
                "workflow_context": "",
                "merged_product_concept": "",
                "mvp_scope": [],
                "source_idea_ids": [],
                "sources": [],
            }
        ],
        min_score=0.45,
    )
    repeated = build_portfolio_cannibalization_from_records(
        buildable_units=list(reversed(units)),
        design_briefs=[
            {
                "id": "dbf-a",
                "title": "Sparse Shared Brief",
                "domain": "ops",
                "theme": "review",
                "mvp_scope": [],
                "source_idea_ids": [],
            }
        ],
        min_score=0.45,
    )

    assert [pair["ids"] for pair in report["pair_findings"]] == [
        ["bu-a", "bu-b"],
        ["bu-a", "bu-c"],
        ["bu-b", "bu-c"],
    ]
    assert report["clusters"][0]["ids"] == ["bu-a", "bu-b", "bu-c"]
    assert report["pair_findings"] == repeated["pair_findings"]
    assert json.loads(json.dumps(report))["summary"]["cluster_count"] == 1


def test_render_cannibalization_report_json_round_trip_and_is_deterministic() -> None:
    report = build_portfolio_cannibalization_from_records(
        buildable_units=[
            _unit(
                "bu-runbook",
                "Incident Runbook Drafter",
                buyer="platform engineering director",
                specific_user="sre lead",
                workflow="incident response handoff",
                problem="SRE leads lose context when incident notes become follow up tasks.",
                solution="Draft runbooks and owners from incident notes.",
            ),
            _unit(
                "bu-retro",
                "Incident Retro Planner",
                buyer="platform engineering director",
                specific_user="sre lead",
                workflow="incident response handoff",
                problem="SRE leads struggle to turn incident notes into retro agendas.",
                solution="Create retrospectives, agenda items, and follow up owner lists.",
            ),
        ],
        design_briefs=[],
    )

    first = render_portfolio_cannibalization_report(report, fmt="json")
    second = render_portfolio_cannibalization_report(report, fmt="json")

    assert first == second
    assert first.endswith("\n")
    parsed = json.loads(first)
    assert parsed == report
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["analyzed_idea_ids"] == ["bu-retro", "bu-runbook"]
    assert parsed["pair_findings"][0]["severity"] in {"low", "medium", "high"}
    assert parsed["recommendations"][0]["action"]


def test_render_cannibalization_report_markdown_remains_supported() -> None:
    report = build_portfolio_cannibalization_from_records(
        buildable_units=[
            _unit(
                "bu-payroll",
                "Payroll Export Cleaner",
                buyer="finance operations director",
                specific_user="payroll analyst",
                workflow="payroll spreadsheet close",
                problem="Payroll teams fix malformed spreadsheet exports before monthly close.",
                solution=(
                    "Normalize payroll CSV exports with field validation and exception review."
                ),
            )
        ],
        design_briefs=[],
    )

    markdown = render_portfolio_cannibalization_report(report)

    assert markdown.endswith("\n")
    assert "# Portfolio Cannibalization Report" in markdown
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "No item pair crossed the cannibalization threshold." in markdown


def test_render_cannibalization_report_rejects_unsupported_format() -> None:
    report = build_portfolio_cannibalization_from_records(
        buildable_units=[],
        design_briefs=[],
    )

    with pytest.raises(ValueError, match="Unsupported portfolio cannibalization format: yaml"):
        render_portfolio_cannibalization_report(report, fmt="yaml")


def _unit(
    unit_id: str,
    title: str,
    *,
    buyer: str,
    specific_user: str,
    workflow: str,
    problem: str,
    solution: str,
    domain: str = "devtools",
    category: BuildableCategory = BuildableCategory.APPLICATION,
    evidence: list[str] | None = None,
    stack: dict | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner=problem,
        category=category,
        problem=problem,
        solution=solution,
        target_users=specific_user,
        value_proposition="Reduce duplicate manual work.",
        specific_user=specific_user,
        buyer=buyer,
        workflow_context=workflow,
        current_workaround=f"Manual {workflow}",
        validation_plan=f"Validate {workflow} with three teams.",
        first_10_customers=buyer,
        evidence_signals=evidence or [],
        tech_approach=solution,
        suggested_stack=stack or {"language": "typescript", "surface": "web"},
        quality_score=7.0,
        usefulness_score=8.0,
        status="approved",
        domain=domain,
    )

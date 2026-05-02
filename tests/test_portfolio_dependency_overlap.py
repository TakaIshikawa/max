"""Tests for portfolio dependency overlap analysis."""

from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis import build_portfolio_dependency_overlap_report as exported_build
from max.analysis import render_portfolio_dependency_overlap_markdown as exported_render
from max.analysis.portfolio_dependency_overlap import (
    SCHEMA_VERSION,
    build_portfolio_dependency_overlap_from_records,
    build_portfolio_dependency_overlap_report,
    render_portfolio_dependency_overlap,
    render_portfolio_dependency_overlap_markdown,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def test_dependency_overlap_groups_shared_stack_across_units_and_briefs(
    store: Store,
) -> None:
    lead = _unit(
        "bu-release-gate",
        "Release Gate",
        stack={"language": "typescript", "ci": "github-action", "runtime": "node"},
        tech="TypeScript GitHub Action that validates release checklists.",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(
        _unit(
            "bu-package-check",
            "Package Check",
            stack={"language": "typescript", "ci": "GitHub Actions", "runtime": "node"},
            tech="Node.js release workflow for GitHub Actions.",
        )
    )
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Release Governance Brief",
            domain="devtools",
            theme="release",
            lead=Candidate(unit=lead),
            readiness_score=84.0,
            why_this_now="Release teams need shared guardrails.",
            merged_product_concept="A GitHub Actions release gate with TypeScript checks.",
            synthesis_rationale="The source ideas depend on the same CI surface.",
            mvp_scope=["GitHub Actions workflow", "TypeScript checklist validation"],
            first_milestones=["Ship the first GitHub Actions gate"],
            validation_plan="Test with two package teams.",
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )

    report = build_portfolio_dependency_overlap_report(store, high_overlap_count=3)

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.portfolio_dependency_overlap"
    assert report["summary"]["total_items"] == 3
    assert report["summary"]["dependency_bucket_count"] >= 2

    github_actions = _bucket(report, "GitHub Actions")
    assert github_actions["overlap_count"] == 3
    assert github_actions["affected_item_ids"] == [
        "bu-package-check",
        "bu-release-gate",
        brief_id,
    ]
    assert github_actions["concentration_risk_level"] == "high"
    assert "fallback path" in github_actions["recommended_action"]
    assert github_actions["source_type_counts"] == [
        {"source_type": "buildable_unit", "count": 2},
        {"source_type": "design_brief", "count": 1},
    ]
    assert json.loads(json.dumps(report))["summary"]["total_items"] == 3


def test_dependency_overlap_domain_filter_and_low_overlap_markdown(store: Store) -> None:
    store.insert_buildable_unit(
        _unit(
            "bu-fastapi-a",
            "FastAPI Reviewer",
            domain="backend",
            stack={"language": "python", "framework": "fastapi", "database": "postgres"},
            tech="FastAPI service backed by PostgreSQL.",
        )
    )
    store.insert_buildable_unit(
        _unit(
            "bu-fastapi-b",
            "FastAPI Cleaner",
            domain="backend",
            stack={"language": "python", "framework": "FastAPI", "database": "sqlite"},
            tech="FastAPI API for cleanup queues.",
        )
    )
    store.insert_buildable_unit(
        _unit(
            "bu-react",
            "React Console",
            domain="devtools",
            stack={"language": "typescript", "frontend": "react"},
            tech="React console for developer workflows.",
        )
    )

    report = build_portfolio_dependency_overlap_report(
        store,
        domain="backend",
        high_overlap_count=3,
    )
    markdown = render_portfolio_dependency_overlap_markdown(report)

    assert report["filters"]["domain"] == ["backend"]
    assert report["summary"]["total_items"] == 2
    assert _bucket(report, "FastAPI")["concentration_risk_level"] == "high"
    assert "# Portfolio Dependency Overlap" in markdown
    assert "Affected items: bu-fastapi-a, bu-fastapi-b" in markdown
    assert "Domain filter: backend" in markdown
    assert markdown == render_portfolio_dependency_overlap_markdown(report)


def test_dependency_overlap_no_shared_dependencies_is_actionable() -> None:
    report = build_portfolio_dependency_overlap_from_records(
        buildable_units=[
            _unit(
                "bu-react-only",
                "React Only",
                stack={"frontend": "react"},
                tech="React UI.",
            ),
            _unit(
                "bu-stripe-only",
                "Stripe Only",
                stack={"payments": "stripe"},
                tech="Stripe billing workflow.",
            ),
        ],
        design_briefs=[],
        min_count=2,
    )

    markdown = render_portfolio_dependency_overlap(report)

    assert report["dependency_buckets"] == []
    assert report["recommendations"][0]["priority"] == "low"
    assert "No dependency or tooling appeared in at least 2 items." in markdown


def test_dependency_overlap_empty_portfolio_markdown_and_json() -> None:
    report = build_portfolio_dependency_overlap_from_records(
        buildable_units=[],
        design_briefs=[],
    )

    markdown = render_portfolio_dependency_overlap_markdown(report)
    rendered_json = render_portfolio_dependency_overlap(report, fmt="json")

    assert report["summary"]["total_items"] == 0
    assert "No portfolio items matched the selected filters." in markdown
    assert json.loads(rendered_json)["kind"] == "max.portfolio_dependency_overlap"


def test_dependency_overlap_exports_from_analysis_package(store: Store) -> None:
    store.insert_buildable_unit(
        _unit(
            "bu-export-a",
            "Export A",
            stack={"language": "python"},
            tech="Python worker.",
        )
    )
    store.insert_buildable_unit(
        _unit(
            "bu-export-b",
            "Export B",
            stack={"language": "python"},
            tech="Python CLI.",
        )
    )

    report = exported_build(store)

    assert _bucket(report, "Python")["overlap_count"] == 2
    assert exported_render(report) == render_portfolio_dependency_overlap_markdown(report)


def test_dependency_overlap_csv_headers_and_bucket_rows(store: Store) -> None:
    store.insert_buildable_unit(
        _unit(
            "bu-csv-a",
            "CSV A",
            domain="backend",
            stack={"language": "python", "framework": "fastapi"},
            tech="FastAPI Python service.",
        )
    )
    store.insert_buildable_unit(
        _unit(
            "bu-csv-b",
            "CSV B",
            domain="backend",
            stack={"language": "python", "framework": "FastAPI"},
            tech="FastAPI Python worker.",
        )
    )

    report = build_portfolio_dependency_overlap_report(store)
    rendered_csv = render_portfolio_dependency_overlap(report, fmt="csv")
    rows = list(csv.DictReader(StringIO(rendered_csv)))

    assert csv.DictReader(StringIO(rendered_csv)).fieldnames == [
        "dependency_name",
        "overlap_count",
        "portfolio_share",
        "concentration_risk_level",
        "affected_item_ids",
        "domains",
        "source_type_counts",
        "recommended_action",
    ]
    fastapi = next(row for row in rows if row["dependency_name"] == "FastAPI")
    assert fastapi["overlap_count"] == "2"
    assert fastapi["portfolio_share"] == "1.0"
    assert fastapi["concentration_risk_level"] == "high"
    assert "fallback path" in fastapi["recommended_action"]


def test_dependency_overlap_csv_serializes_multi_value_fields(store: Store) -> None:
    lead = _unit(
        "bu-csv-release",
        "CSV Release",
        stack={"language": "typescript", "ci": "github-action"},
        tech="TypeScript GitHub Action release gate.",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(
        _unit(
            "bu-csv-package",
            "CSV Package",
            stack={"language": "typescript", "ci": "GitHub Actions"},
            tech="GitHub Actions package workflow.",
        )
    )
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="CSV Governance Brief",
            domain="devtools",
            theme="release",
            lead=Candidate(unit=lead),
            readiness_score=84.0,
            why_this_now="Release teams need shared guardrails.",
            merged_product_concept="A GitHub Actions release gate with TypeScript checks.",
            synthesis_rationale="The source ideas depend on the same CI surface.",
            mvp_scope=["GitHub Actions workflow"],
            first_milestones=["Ship the first GitHub Actions gate"],
            validation_plan="Test with two package teams.",
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )

    report = build_portfolio_dependency_overlap_report(store, high_overlap_count=3)
    rows = list(
        csv.DictReader(StringIO(render_portfolio_dependency_overlap(report, fmt="csv")))
    )
    github_actions = next(row for row in rows if row["dependency_name"] == "GitHub Actions")

    assert json.loads(github_actions["affected_item_ids"]) == [
        "bu-csv-package",
        "bu-csv-release",
        brief_id,
    ]
    assert json.loads(github_actions["domains"]) == ["devtools"]
    assert json.loads(github_actions["source_type_counts"]) == [
        {"count": 2, "source_type": "buildable_unit"},
        {"count": 1, "source_type": "design_brief"},
    ]


def test_dependency_overlap_csv_empty_bucket_output_has_header_only() -> None:
    report = build_portfolio_dependency_overlap_from_records(
        buildable_units=[
            _unit(
                "bu-csv-react-only",
                "CSV React Only",
                stack={"frontend": "react"},
                tech="React UI.",
            )
        ],
        design_briefs=[],
        min_count=2,
    )

    rendered_csv = render_portfolio_dependency_overlap(report, fmt="csv")

    assert list(csv.DictReader(StringIO(rendered_csv))) == []
    assert rendered_csv == (
        "dependency_name,overlap_count,portfolio_share,concentration_risk_level,"
        "affected_item_ids,domains,source_type_counts,recommended_action\n"
    )


def test_dependency_overlap_unsupported_format_error() -> None:
    report = build_portfolio_dependency_overlap_from_records(
        buildable_units=[],
        design_briefs=[],
    )

    with pytest.raises(
        ValueError,
        match="Unsupported portfolio dependency overlap format: yaml",
    ):
        render_portfolio_dependency_overlap(report, fmt="yaml")


def _bucket(report: dict, dependency_name: str) -> dict:
    return next(
        bucket
        for bucket in report["dependency_buckets"]
        if bucket["dependency_name"] == dependency_name
    )


def _unit(
    unit_id: str,
    title: str,
    *,
    stack: dict,
    tech: str,
    domain: str = "devtools",
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner=f"{title} for platform teams",
        category=BuildableCategory.APPLICATION,
        problem="Teams need clearer implementation reuse signals.",
        solution=tech,
        target_users="platform operators",
        value_proposition="Reduce duplicate platform choices.",
        specific_user="platform lead",
        buyer="engineering leadership",
        workflow_context="portfolio review",
        tech_approach=tech,
        suggested_stack=stack,
        composability_notes="Designed for reuse across generated specs.",
        quality_score=7.6,
        usefulness_score=7.8,
        status="approved",
        domain=domain,
    )

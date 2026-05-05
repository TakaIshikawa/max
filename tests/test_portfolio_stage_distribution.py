"""Tests for portfolio stage distribution reporting."""

from __future__ import annotations

import copy
import csv
import io
import json

import pytest

from max.analysis.portfolio_stage_distribution import (
    SCHEMA_VERSION,
    build_portfolio_stage_distribution_report,
    render_portfolio_stage_distribution_json,
    render_portfolio_stage_distribution_report,
)
from max.types.evaluation import DimensionScore, UtilityEvaluation


def test_report_groups_status_recommendation_profile_domain_and_evidence_strength() -> None:
    report = build_portfolio_stage_distribution_report(
        [
            _unit(
                "bu-review-1",
                status="evaluated",
                domain="developer-tools",
                profile="platform",
                evidence_signals=["sig-1", "sig-2"],
                inspiring_insights=["ins-1"],
                source_idea_ids=["bu-source"],
            ),
            _unit(
                "bu-build-1",
                status="approved",
                domain="developer-tools",
                profile="platform",
                evidence_signals=["sig-3"],
            ),
            _unit("bu-publish-1", status="published", domain="finops", profile="finance"),
        ],
        {
            "bu-review-1": _evaluation("bu-review-1", recommendation="yes"),
            "bu-build-1": _evaluation("bu-build-1", recommendation="maybe"),
            "bu-publish-1": _evaluation("bu-publish-1", recommendation="yes"),
        },
    )

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.portfolio_stage_distribution"
    assert report["summary"]["total_ideas"] == 3
    assert report["summary"]["evaluated_count"] == 3
    assert _bucket(report["by_status"], "status", "evaluated") == {
        "status": "evaluated",
        "count": 1,
        "percentage": 33.3,
    }
    assert _bucket(report["by_recommendation"], "recommendation", "yes")["count"] == 2
    assert _bucket(report["by_profile"], "profile", "platform")["count"] == 2
    assert _bucket(report["by_domain"], "domain", "developer-tools")["percentage"] == 66.7
    assert _bucket(report["by_evidence_strength"], "evidence_strength", "strong")["count"] == 1
    assert _bucket(report["by_evidence_strength"], "evidence_strength", "weak")["count"] == 1
    assert _bucket(report["by_evidence_strength"], "evidence_strength", "none")["count"] == 1
    assert {
        "status": "evaluated",
        "recommendation": "yes",
        "profile": "platform",
        "domain": "developer-tools",
        "evidence_strength": "strong",
        "count": 1,
        "percentage": 33.3,
    } in report["groups"]
    assert json.loads(json.dumps(report))["summary"]["total_ideas"] == 3


def test_report_identifies_bottleneck_recommendation_when_stage_dominates() -> None:
    units = [
        _unit("bu-draft-1", status="draft"),
        _unit("bu-draft-2", status="draft"),
        _unit("bu-draft-3", status="draft"),
        _unit("bu-approved-1", status="approved"),
    ]

    report = build_portfolio_stage_distribution_report(
        units,
        {"bu-approved-1": _evaluation("bu-approved-1", recommendation="yes")},
    )

    status_bottleneck = next(
        item for item in report["bottlenecks"] if item["dimension"] == "status"
    )
    assert status_bottleneck["value"] == "draft"
    assert status_bottleneck["count"] == 3
    assert status_bottleneck["percentage"] == 75.0
    assert any("promote, validate, or prune" in item for item in report["recommendations"])
    assert any(
        item["dimension"] == "recommendation" and item["value"] == "unevaluated"
        for item in report["bottlenecks"]
    )


def test_filtering_by_profile_and_domain_changes_totals_without_mutating_inputs() -> None:
    units = [
        _unit("bu-platform-1", profile="platform", domain="developer-tools", status="approved"),
        _unit("bu-platform-2", profile="platform", domain="finops", status="approved"),
        _unit("bu-finance-1", profile="finance", domain="finops", status="published"),
    ]
    original = copy.deepcopy(units)

    report = build_portfolio_stage_distribution_report(
        units,
        [_evaluation("bu-platform-1", recommendation="yes")],
        profile="platform",
        domain="developer-tools",
    )

    assert report["filters"] == {"profile": ["platform"], "domain": ["developer-tools"]}
    assert report["summary"]["total_ideas"] == 1
    assert report["summary"]["evaluated_count"] == 1
    assert _bucket(report["by_domain"], "domain", "developer-tools")["count"] == 1
    assert units == original

    unfiltered = build_portfolio_stage_distribution_report(units, [])
    assert unfiltered["summary"]["total_ideas"] == 3


def test_ideas_without_evaluations_are_counted_in_explicit_unevaluated_bucket() -> None:
    report = build_portfolio_stage_distribution_report(
        [
            _unit("bu-evaluated", status="evaluated"),
            _unit("bu-unevaluated", status="draft"),
        ],
        [_evaluation("bu-evaluated", recommendation="no")],
    )

    assert report["summary"]["unevaluated_count"] == 1
    assert _bucket(report["by_recommendation"], "recommendation", "unevaluated") == {
        "recommendation": "unevaluated",
        "count": 1,
        "percentage": 50.0,
    }
    assert any(group["recommendation"] == "unevaluated" for group in report["groups"])


def test_render_report_json_is_deterministic_and_round_trips() -> None:
    report = build_portfolio_stage_distribution_report(
        [_unit("bu-approved", status="approved")],
        [_evaluation("bu-approved", recommendation="yes")],
    )

    rendered = render_portfolio_stage_distribution_report(report)

    assert rendered == render_portfolio_stage_distribution_report(report, fmt="json")
    assert rendered.endswith("\n")
    assert json.loads(rendered) == report
    assert rendered.index('"by_domain"') < rendered.index('"by_evidence_strength"')


def test_render_report_markdown_includes_filters_summary_bottlenecks_and_buckets() -> None:
    report = build_portfolio_stage_distribution_report(
        [
            _unit("bu-draft-1", status="draft", domain="developer-tools", profile="platform"),
            _unit("bu-draft-2", status="draft", domain="developer-tools", profile="platform"),
            _unit("bu-approved-1", status="approved", domain="developer-tools", profile="platform"),
        ],
        {"bu-approved-1": _evaluation("bu-approved-1", recommendation="yes")},
        profile="platform",
        domain="developer-tools",
    )

    markdown = render_portfolio_stage_distribution_report(report, fmt="markdown")

    assert markdown.startswith("# Portfolio Stage Distribution\n")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "Profile filter: platform" in markdown
    assert "Domain filter: developer-tools" in markdown
    assert "- Total ideas: 3" in markdown
    assert "- Evaluated ideas: 1" in markdown
    assert "## Bottlenecks" in markdown
    assert "- status=draft: 2 ideas (66.7%)" in markdown
    assert "## Recommendations" in markdown
    assert "promote, validate, or prune" in markdown
    assert "### Status" in markdown
    assert "| draft | 2 | 66.7% |" in markdown
    assert "### Recommendation" in markdown
    assert "### Profile" in markdown
    assert "### Domain" in markdown
    assert "### Evidence Strength" in markdown


def test_render_report_csv_uses_stable_header_and_row_types() -> None:
    report = build_portfolio_stage_distribution_report(
        [
            _unit("bu-draft-1", status="draft"),
            _unit("bu-draft-2", status="draft"),
            _unit("bu-approved-1", status="approved"),
        ],
        {"bu-approved-1": _evaluation("bu-approved-1", recommendation="yes")},
    )

    rendered = render_portfolio_stage_distribution_report(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(rendered)))

    assert rendered.splitlines()[0] == (
        "row_type,dimension,value,status,recommendation,profile,domain,"
        "evidence_strength,count,percentage,message"
    )
    assert render_portfolio_stage_distribution_report(report, fmt="csv") == rendered
    assert {"bucket", "group", "bottleneck", "recommendation"}.issubset(
        {row["row_type"] for row in rows}
    )
    assert any(
        row["row_type"] == "bucket"
        and row["dimension"] == "status"
        and row["value"] == "draft"
        and row["count"] == "2"
        for row in rows
    )
    assert any(
        row["row_type"] == "group"
        and row["status"] == "approved"
        and row["recommendation"] == "yes"
        for row in rows
    )
    assert any(
        row["row_type"] == "bottleneck"
        and row["dimension"] == "status"
        and "promote, validate, or prune" in row["message"]
        for row in rows
    )
    assert any(
        row["row_type"] == "recommendation"
        and "promote, validate, or prune" in row["message"]
        for row in rows
    )


def test_render_report_rejects_unsupported_format() -> None:
    report = build_portfolio_stage_distribution_report([], [])

    with pytest.raises(ValueError, match="Unsupported portfolio stage distribution format: yaml"):
        render_portfolio_stage_distribution_report(report, fmt="yaml")


def _unit(
    unit_id: str,
    *,
    status: str,
    domain: str = "developer-tools",
    profile: str = "platform",
    evidence_signals: list[str] | None = None,
    inspiring_insights: list[str] | None = None,
    source_idea_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": unit_id,
        "title": f"Idea {unit_id}",
        "one_liner": "Report idea portfolio stage distribution",
        "category": "workflow",
        "problem": "Portfolio operators cannot see where ideas are stuck.",
        "solution": "Summarize status, recommendation, and evidence distribution.",
        "value_proposition": "Make promote and prune decisions easier.",
        "profile": profile,
        "domain": domain,
        "status": status,
        "evidence_signals": evidence_signals or [],
        "inspiring_insights": inspiring_insights or [],
        "source_idea_ids": source_idea_ids or [],
    }


def _evaluation(unit_id: str, *, recommendation: str) -> UtilityEvaluation:
    dim = DimensionScore(value=7.0, confidence=0.8, reasoning="clear")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=dim,
        timing_fit=dim,
        compounding_value=dim,
        overall_score=72.0,
        recommendation=recommendation,
    )


def _bucket(rows: list[dict], key: str, value: str) -> dict:
    return next(row for row in rows if row[key] == value)


def test_render_portfolio_stage_distribution_json_produces_valid_json() -> None:
    """Verify JSON renderer produces valid, deterministic JSON output."""
    report = build_portfolio_stage_distribution_report(
        [
            _unit("bu-approved", status="approved", domain="analytics", profile="platform"),
            _unit("bu-draft", status="draft", domain="finops", profile="finance"),
        ],
        [
            _evaluation("bu-approved", recommendation="yes"),
            _evaluation("bu-draft", recommendation="maybe"),
        ],
    )

    json_output = render_portfolio_stage_distribution_json(report)

    # Should be valid JSON
    parsed = json.loads(json_output)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == "max.portfolio_stage_distribution"
    assert parsed["summary"]["total_ideas"] == 2
    assert parsed["summary"]["evaluated_count"] == 2

    # Should be deterministic
    assert render_portfolio_stage_distribution_json(report) == json_output

    # Should end with newline
    assert json_output.endswith("\n")

    # Should be sorted and indented
    assert '"by_domain"' in json_output
    assert json_output.index('"by_domain"') < json_output.index('"by_evidence_strength"')

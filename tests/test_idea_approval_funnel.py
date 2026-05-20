from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.idea_approval_funnel import (
    KIND,
    SCHEMA_VERSION,
    build_idea_approval_funnel,
    render_idea_approval_funnel,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


def test_build_idea_approval_funnel_counts_and_sorts_breakdowns(store: Store) -> None:
    _seed_funnel(store)

    report = build_idea_approval_funnel(store, limit=10)
    repeated = build_idea_approval_funnel(store, limit=10)

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert set(report) == {
        "schema_version",
        "kind",
        "filters",
        "summary",
        "stages",
        "category_breakdown",
        "domain_breakdown",
        "next_actions",
    }
    assert report["stages"] == {
        "generated": 5,
        "evaluated": 4,
        "recommended": 3,
        "approved_or_published": 2,
        "rejected": 1,
        "publication_attempted": 2,
    }
    assert report["summary"]["approval_rate"] == pytest.approx(0.667)
    assert [row["category"] for row in report["category_breakdown"]] == [
        "integration",
        "cli_tool",
        "automation",
    ]
    assert [row["domain"] for row in report["domain_breakdown"]] == [
        "security",
        "analytics",
    ]


def test_idea_approval_funnel_filters_and_renders(store: Store) -> None:
    _seed_funnel(store)

    report = build_idea_approval_funnel(store, domain="analytics")

    assert report["summary"]["generated"] == 3
    assert json.loads(render_idea_approval_funnel(report, fmt="json")) == report
    markdown = render_idea_approval_funnel(report, fmt="markdown")
    assert markdown.startswith("# Idea Approval Funnel")
    assert "## Category Breakdown" in markdown
    rows = list(csv.DictReader(StringIO(render_idea_approval_funnel(report, fmt="csv"))))
    assert rows[0]["section"] == "summary"
    assert any(row["section"] == "category" and row["key"] == "cli_tool" for row in rows)

    with pytest.raises(ValueError, match="Unsupported idea approval funnel format: yaml"):
        render_idea_approval_funnel(report, fmt="yaml")
    with pytest.raises(ValueError, match="limit must be at least 1"):
        build_idea_approval_funnel(store, limit=0)


def _seed_funnel(store: Store) -> None:
    rows = [
        ("idea-a", BuildableCategory.CLI_TOOL, "analytics", "evaluated", "yes", "approved", True),
        ("idea-b", BuildableCategory.CLI_TOOL, "analytics", "evaluated", "strong_yes", None, False),
        ("idea-c", BuildableCategory.AUTOMATION, "analytics", "published", "yes", "published", True),
        ("idea-d", BuildableCategory.INTEGRATION, "security", "rejected", "no", "rejected", False),
        ("idea-e", BuildableCategory.INTEGRATION, "security", "draft", None, None, False),
    ]
    for idea_id, category, domain, status, recommendation, outcome, published in rows:
        store.insert_buildable_unit(_unit(idea_id, category, domain, status))
        if recommendation:
            store.insert_evaluation(_evaluation(idea_id, recommendation))
        if outcome:
            store.insert_feedback(idea_id, outcome, reason=f"{outcome} reason")
        if published:
            store.insert_publication_attempt(
                idea_id=idea_id,
                target_type="linear",
                target_url=f"https://linear.example/{idea_id}",
                status="published" if outcome == "published" else "failed",
                error="" if outcome == "published" else "rate limited",
            )


def _unit(idea_id: str, category: BuildableCategory, domain: str, status: str) -> BuildableUnit:
    return BuildableUnit(
        id=idea_id,
        title=idea_id,
        one_liner="one",
        category=category,
        problem="problem",
        solution="solution",
        value_proposition="value",
        domain=domain,
        status=status,
    )


def _evaluation(idea_id: str, recommendation: str) -> UtilityEvaluation:
    score = DimensionScore(value=8.0, confidence=0.8, reasoning="seed")
    return UtilityEvaluation(
        buildable_unit_id=idea_id,
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=80.0,
        strengths=[],
        weaknesses=[],
        recommendation=recommendation,
        weights_used={},
    )

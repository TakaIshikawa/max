"""Tests for technical debt tracking report export module."""

import pytest

from max.exports.technical_debt_report import (
    build_technical_debt_report,
    render_technical_debt_markdown,
    _score_debt_items,
    _prioritize_debt,
    _group_by_category,
    _build_summary,
)


@pytest.fixture
def debt_items():
    return [
        {
            "name": "Monolithic service class",
            "category": "architecture",
            "effort_hours": 40,
            "impact": 5,
            "description": "Core service class exceeds 2000 lines",
            "affected_components": ["api", "core"],
        },
        {
            "name": "Missing unit tests for auth",
            "category": "coverage",
            "effort_hours": 8,
            "impact": 4,
            "description": "Auth module has 20% test coverage",
            "affected_components": ["auth"],
        },
        {
            "name": "Deprecated ORM version",
            "category": "dependency",
            "effort_hours": 16,
            "impact": 3,
            "description": "Using ORM v2 which is EOL",
            "affected_components": ["database", "models"],
        },
        {
            "name": "Nested callback hell",
            "category": "complexity",
            "effort_hours": 4,
            "impact": 3,
            "description": "Deeply nested async callbacks in event handler",
            "affected_components": ["events"],
        },
        {
            "name": "Hardcoded config values",
            "category": "architecture",
            "effort_hours": 2,
            "impact": 2,
            "description": "Config values hardcoded instead of env vars",
            "affected_components": ["config"],
        },
    ]


class TestScoreDebtItems:
    def test_payoff_ratio_calculation(self, debt_items):
        scored = _score_debt_items(debt_items)
        # "Missing unit tests": impact=4, effort=8 → ratio=0.5
        auth_item = next(s for s in scored if s["name"] == "Missing unit tests for auth")
        assert auth_item["payoff_ratio"] == pytest.approx(0.5)

    def test_severity_score(self, debt_items):
        scored = _score_debt_items(debt_items)
        monolith = next(s for s in scored if s["name"] == "Monolithic service class")
        assert monolith["severity_score"] == 25  # impact 5 * 5

    def test_high_payoff_for_low_effort_high_impact(self):
        items = [{"name": "Quick win", "category": "complexity", "effort_hours": 1, "impact": 5, "description": "x", "affected_components": []}]
        scored = _score_debt_items(items)
        assert scored[0]["payoff_ratio"] == 5.0

    def test_empty_items(self):
        assert _score_debt_items([]) == []


class TestPrioritizeDebt:
    def test_sorted_by_payoff_ratio_desc(self, debt_items):
        scored = _score_debt_items(debt_items)
        prioritized = _prioritize_debt(scored)
        ratios = [p["payoff_ratio"] for p in prioritized]
        assert ratios == sorted(ratios, reverse=True)

    def test_highest_priority_item(self, debt_items):
        scored = _score_debt_items(debt_items)
        prioritized = _prioritize_debt(scored)
        # "Hardcoded config": impact=2, effort=2 → ratio=1.0
        # "Nested callbacks": impact=3, effort=4 → ratio=0.75
        # "Missing tests": impact=4, effort=8 → ratio=0.5
        # Highest should be "Hardcoded config" at 1.0
        assert prioritized[0]["name"] == "Hardcoded config values"


class TestGroupByCategory:
    def test_groups_correctly(self, debt_items):
        scored = _score_debt_items(debt_items)
        groups = _group_by_category(scored)
        assert len(groups["architecture"]) == 2
        assert len(groups["coverage"]) == 1
        assert len(groups["dependency"]) == 1
        assert len(groups["complexity"]) == 1

    def test_empty_categories_present(self):
        scored = _score_debt_items([
            {"name": "X", "category": "coverage", "effort_hours": 1, "impact": 1, "description": "", "affected_components": []}
        ])
        groups = _group_by_category(scored)
        assert "architecture" in groups
        assert groups["architecture"] == []


class TestBuildSummary:
    def test_summary_totals(self, debt_items):
        scored = _score_debt_items(debt_items)
        summary = _build_summary(scored)
        assert summary["total_items"] == 5
        assert summary["total_effort_hours"] == 70  # 40+8+16+4+2

    def test_avg_payoff_ratio(self, debt_items):
        scored = _score_debt_items(debt_items)
        summary = _build_summary(scored)
        # Calculate expected: (5/40 + 4/8 + 3/16 + 3/4 + 2/2) / 5
        expected = (0.125 + 0.5 + 0.1875 + 0.75 + 1.0) / 5
        assert summary["avg_payoff_ratio"] == pytest.approx(expected, rel=1e-3)

    def test_highest_priority_category(self, debt_items):
        scored = _score_debt_items(debt_items)
        summary = _build_summary(scored)
        # complexity has ratio 0.75, architecture has (0.125+1.0)/2=0.5625
        # coverage has 0.5, dependency has 0.1875
        assert summary["highest_priority_category"] == "complexity"

    def test_empty_items(self):
        summary = _build_summary([])
        assert summary["total_items"] == 0
        assert summary["total_effort_hours"] == 0.0
        assert summary["highest_priority_category"] == "none"


class TestBuildTechnicalDebtReport:
    def test_report_structure(self, debt_items):
        report = build_technical_debt_report(debt_items)
        assert report["schema_version"] == "max.technical_debt_report.v1"
        assert report["kind"] == "max.technical_debt_report"
        assert "debt_items" in report
        assert "prioritized" in report
        assert "by_category" in report
        assert "summary" in report

    def test_prioritized_order(self, debt_items):
        report = build_technical_debt_report(debt_items)
        ratios = [p["payoff_ratio"] for p in report["prioritized"]]
        assert ratios == sorted(ratios, reverse=True)

    def test_all_items_scored(self, debt_items):
        report = build_technical_debt_report(debt_items)
        assert all("payoff_ratio" in item for item in report["debt_items"])
        assert all("severity_score" in item for item in report["debt_items"])


class TestRenderMarkdown:
    def test_renders_without_error(self, debt_items):
        report = build_technical_debt_report(debt_items)
        md = render_technical_debt_markdown(report)
        assert "# Technical Debt Report" in md
        assert "## Summary" in md
        assert "## Prioritized Debt Items" in md
        assert "## Debt by Category" in md

    def test_contains_item_data(self, debt_items):
        report = build_technical_debt_report(debt_items)
        md = render_technical_debt_markdown(report)
        assert "Monolithic service class" in md
        assert "architecture" in md

    def test_contains_summary_stats(self, debt_items):
        report = build_technical_debt_report(debt_items)
        md = render_technical_debt_markdown(report)
        assert "Total debt items: 5" in md
        assert "70.0h" in md

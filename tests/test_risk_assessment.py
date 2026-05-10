"""Tests for risk assessment report export module."""

import pytest

from max.exports.risk_assessment import (
    build_risk_assessment_report,
    render_risk_assessment_markdown,
    _score_risks,
    _risk_level,
    _categorize_risks,
    _get_high_priority_risks,
    _generate_mitigations,
)


@pytest.fixture
def risks():
    return [
        {
            "name": "Database migration failure",
            "category": "technical",
            "severity": 5,
            "probability": 4,
            "description": "Complex schema migration may fail in production",
            "mitigation": "Run migration on staging first with rollback plan",
        },
        {
            "name": "Key developer unavailable",
            "category": "resource",
            "severity": 4,
            "probability": 3,
            "description": "Single point of failure for critical component",
            "mitigation": None,
        },
        {
            "name": "Deadline too aggressive",
            "category": "timeline",
            "severity": 3,
            "probability": 4,
            "description": "Timeline does not account for testing phase",
            "mitigation": "Negotiate scope reduction with stakeholders",
        },
        {
            "name": "Third-party API deprecation",
            "category": "dependency",
            "severity": 4,
            "probability": 2,
            "description": "Vendor may deprecate v2 API before migration",
            "mitigation": None,
        },
        {
            "name": "Minor UI inconsistency",
            "category": "technical",
            "severity": 1,
            "probability": 2,
            "description": "Button styles differ across pages",
            "mitigation": None,
        },
    ]


class TestScoreRisks:
    def test_score_calculation(self, risks):
        scored = _score_risks(risks)
        db_risk = next(r for r in scored if r["name"] == "Database migration failure")
        assert db_risk["risk_score"] == 20  # 5 * 4

    def test_sorted_by_score_desc(self, risks):
        scored = _score_risks(risks)
        scores = [r["risk_score"] for r in scored]
        assert scores == sorted(scores, reverse=True)

    def test_risk_level_assigned(self, risks):
        scored = _score_risks(risks)
        db_risk = next(r for r in scored if r["name"] == "Database migration failure")
        assert db_risk["risk_level"] == "critical"


class TestRiskLevel:
    def test_critical(self):
        assert _risk_level(20) == "critical"
        assert _risk_level(25) == "critical"

    def test_high(self):
        assert _risk_level(12) == "high"
        assert _risk_level(19) == "high"

    def test_medium(self):
        assert _risk_level(6) == "medium"
        assert _risk_level(11) == "medium"

    def test_low(self):
        assert _risk_level(1) == "low"
        assert _risk_level(5) == "low"


class TestCategorizeRisks:
    def test_categories(self, risks):
        scored = _score_risks(risks)
        categorized = _categorize_risks(scored)
        assert len(categorized["technical"]) == 2
        assert len(categorized["resource"]) == 1
        assert len(categorized["timeline"]) == 1
        assert len(categorized["dependency"]) == 1

    def test_empty_risks(self):
        categorized = _categorize_risks([])
        for cat in ("technical", "resource", "timeline", "dependency"):
            assert categorized[cat] == []


class TestGetHighPriorityRisks:
    def test_filters_high_and_critical(self, risks):
        scored = _score_risks(risks)
        high = _get_high_priority_risks(scored)
        # score >= 12: DB(20), developer(12), deadline(12)
        assert len(high) == 3
        assert all(r["risk_score"] >= 12 for r in high)

    def test_excludes_low_risks(self, risks):
        scored = _score_risks(risks)
        high = _get_high_priority_risks(scored)
        names = [r["name"] for r in high]
        assert "Minor UI inconsistency" not in names


class TestGenerateMitigations:
    def test_uses_provided_mitigation(self, risks):
        scored = _score_risks(risks)
        high = _get_high_priority_risks(scored)
        mitigations = _generate_mitigations(high)
        db_mit = next(m for m in mitigations if m["risk_name"] == "Database migration failure")
        assert db_mit["strategy"] == "Run migration on staging first with rollback plan"

    def test_generates_default_mitigation(self, risks):
        scored = _score_risks(risks)
        high = _get_high_priority_risks(scored)
        mitigations = _generate_mitigations(high)
        dev_mit = next(m for m in mitigations if m["risk_name"] == "Key developer unavailable")
        assert "Cross-train" in dev_mit["strategy"]

    def test_priority_levels(self, risks):
        scored = _score_risks(risks)
        high = _get_high_priority_risks(scored)
        mitigations = _generate_mitigations(high)
        db_mit = next(m for m in mitigations if m["risk_name"] == "Database migration failure")
        assert db_mit["priority"] == "immediate"  # score 20

        dev_mit = next(m for m in mitigations if m["risk_name"] == "Key developer unavailable")
        assert dev_mit["priority"] == "high"  # score 12


class TestBuildRiskAssessmentReport:
    def test_report_structure(self, risks):
        report = build_risk_assessment_report(risks)
        assert report["schema_version"] == "max.risk_assessment.v1"
        assert report["kind"] == "max.risk_assessment"
        assert "risk_matrix" in report
        assert "categorized_risks" in report
        assert "high_priority_risks" in report
        assert "mitigation_strategies" in report
        assert "summary" in report

    def test_summary_counts(self, risks):
        report = build_risk_assessment_report(risks)
        summary = report["summary"]
        assert summary["total_risks"] == 5
        assert summary["critical_count"] == 1
        assert summary["high_count"] == 2
        assert summary["medium_count"] == 1
        assert summary["low_count"] == 1

    def test_risk_matrix_sorted(self, risks):
        report = build_risk_assessment_report(risks)
        scores = [r["risk_score"] for r in report["risk_matrix"]]
        assert scores == sorted(scores, reverse=True)


class TestRenderMarkdown:
    def test_renders_without_error(self, risks):
        report = build_risk_assessment_report(risks)
        md = render_risk_assessment_markdown(report)
        assert "# Risk Assessment Report" in md
        assert "## Summary" in md
        assert "## Risk Matrix" in md

    def test_contains_risk_data(self, risks):
        report = build_risk_assessment_report(risks)
        md = render_risk_assessment_markdown(report)
        assert "Database migration failure" in md
        assert "critical" in md

    def test_contains_mitigations(self, risks):
        report = build_risk_assessment_report(risks)
        md = render_risk_assessment_markdown(report)
        assert "## Mitigation Strategies" in md
        assert "Run migration on staging first" in md

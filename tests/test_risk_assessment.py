"""Tests for risk assessment report export."""

from __future__ import annotations

import json

from max.exports.risk_assessment import (
    KIND,
    SCHEMA_VERSION,
    build_risk_assessment,
    compute_risk_score,
    render_risk_json,
    render_risk_markdown,
    risk_priority,
)

# ── Test Data ────────────────────────────────────────────────────────

SAMPLE_RISKS = [
    {
        "title": "Database migration failure",
        "description": "Schema changes may cause data loss during migration",
        "category": "technical",
        "severity": "critical",
        "probability": "possible",
        "mitigation": "Run migrations in staging first, maintain rollback scripts",
    },
    {
        "title": "Key developer departure",
        "description": "Single point of failure on auth module",
        "category": "resource",
        "severity": "high",
        "probability": "unlikely",
        "mitigation": "Cross-train team members on critical modules",
    },
    {
        "title": "Deadline overrun",
        "description": "Scope creep may delay Q3 release",
        "category": "timeline",
        "severity": "medium",
        "probability": "likely",
        "mitigation": "Enforce scope freeze, weekly progress reviews",
    },
    {
        "title": "Third-party API deprecation",
        "description": "Payment provider v1 API end-of-life in 6 months",
        "category": "dependency",
        "severity": "high",
        "probability": "almost_certain",
        "mitigation": "Begin migration to v2 API immediately",
    },
    {
        "title": "Minor logging gap",
        "category": "technical",
        "severity": "low",
        "probability": "unlikely",
    },
]


# ── compute_risk_score tests ────────────────────────────────────────


def test_score_low_unlikely() -> None:
    assert compute_risk_score("low", "unlikely") == 1


def test_score_critical_almost_certain() -> None:
    assert compute_risk_score("critical", "almost_certain") == 16


def test_score_high_possible() -> None:
    assert compute_risk_score("high", "possible") == 6


def test_score_medium_likely() -> None:
    assert compute_risk_score("medium", "likely") == 6


# ── risk_priority tests ─────────────────────────────────────────────


def test_priority_high() -> None:
    assert risk_priority(9) == "high"
    assert risk_priority(16) == "high"


def test_priority_medium() -> None:
    assert risk_priority(4) == "medium"
    assert risk_priority(8) == "medium"


def test_priority_low() -> None:
    assert risk_priority(1) == "low"
    assert risk_priority(3) == "low"


# ── build_risk_assessment tests ─────────────────────────────────────


def test_build_schema() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS)
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["kind"] == KIND
    assert "generated_at" in doc


def test_build_project_name() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS, project_name="TestProject")
    assert doc["project_name"] == "TestProject"


def test_build_risk_count() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS)
    assert len(doc["risks"]) == 5


def test_build_sorted_by_score_desc() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS)
    scores = [r["score"] for r in doc["risks"]]
    assert scores == sorted(scores, reverse=True)


def test_build_categories() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS)
    by_cat = doc["by_category"]
    assert len(by_cat["technical"]) == 2
    assert len(by_cat["resource"]) == 1
    assert len(by_cat["timeline"]) == 1
    assert len(by_cat["dependency"]) == 1


def test_build_high_priority_risks() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS)
    high = doc["high_priority_risks"]
    assert all(r["priority"] == "high" for r in high)
    assert len(high) >= 1


def test_build_summary() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS)
    summary = doc["summary"]
    assert summary["total"] == 5
    assert summary["high"] + summary["medium"] + summary["low"] == 5


def test_build_invalid_category_defaults() -> None:
    risks = [{"title": "X", "category": "invalid"}]
    doc = build_risk_assessment(risks)
    assert doc["risks"][0]["category"] == "technical"


def test_build_invalid_severity_defaults() -> None:
    risks = [{"title": "X", "severity": "extreme"}]
    doc = build_risk_assessment(risks)
    assert doc["risks"][0]["severity"] == "medium"


def test_build_empty() -> None:
    doc = build_risk_assessment([])
    assert doc["risks"] == []
    assert doc["summary"]["total"] == 0


def test_build_mitigation_included() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS)
    db_risk = next(r for r in doc["risks"] if r["title"] == "Database migration failure")
    assert "rollback" in db_risk["mitigation"]


# ── Markdown rendering ──────────────────────────────────────────────


def test_render_markdown_title() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS, project_name="TestApp")
    md = render_risk_markdown(doc)
    assert "# Risk Assessment — TestApp" in md


def test_render_markdown_summary() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS)
    md = render_risk_markdown(doc)
    assert "Total risks identified: 5" in md


def test_render_markdown_high_priority_section() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS)
    md = render_risk_markdown(doc)
    assert "## High Priority Risks" in md


def test_render_markdown_risk_details() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS)
    md = render_risk_markdown(doc)
    assert "Database migration failure" in md
    assert "**Severity**: critical" in md
    assert "**Mitigation**:" in md


def test_render_markdown_category_sections() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS)
    md = render_risk_markdown(doc)
    assert "## Technical Risks" in md
    assert "## Resource Risks" in md


# ── JSON rendering ──────────────────────────────────────────────────


def test_render_json_valid() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS)
    output = render_risk_json(doc)
    parsed = json.loads(output)
    assert parsed["schema_version"] == SCHEMA_VERSION


def test_render_json_roundtrip() -> None:
    doc = build_risk_assessment(SAMPLE_RISKS, project_name="App")
    output = render_risk_json(doc)
    parsed = json.loads(output)
    assert parsed["project_name"] == "App"
    assert len(parsed["risks"]) == 5

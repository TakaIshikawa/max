"""Tests for technical debt tracking report export."""

from __future__ import annotations

import json

from max.exports.technical_debt_report import (
    KIND,
    SCHEMA_VERSION,
    build_debt_report,
    compute_payoff_ratio,
    render_debt_json,
    render_debt_markdown,
)

# ── Test Data ────────────────────────────────────────────────────────

SAMPLE_DEBT_ITEMS = [
    {
        "title": "Monolithic auth module",
        "description": "Auth module has grown to 3000 lines, needs decomposition",
        "category": "architecture",
        "severity": "high",
        "impact": 0.9,
        "effort": 0.7,
        "location": "src/auth/handler.py",
    },
    {
        "title": "Missing API integration tests",
        "description": "No integration tests for payment endpoints",
        "category": "test_coverage",
        "severity": "medium",
        "impact": 0.6,
        "effort": 0.3,
        "location": "tests/integration/",
    },
    {
        "title": "Legacy ORM queries",
        "description": "Raw SQL mixed with ORM calls in data layer",
        "category": "code_complexity",
        "severity": "medium",
        "impact": 0.5,
        "effort": 0.5,
    },
    {
        "title": "Deprecated requests library version",
        "description": "Using requests 2.25 with known CVE",
        "category": "deprecated_dependency",
        "severity": "critical",
        "impact": 0.8,
        "effort": 0.2,
        "location": "requirements.txt",
    },
    {
        "title": "Unused utility functions",
        "category": "code_complexity",
        "severity": "low",
        "impact": 0.1,
        "effort": 0.1,
    },
]


# ── compute_payoff_ratio tests ──────────────────────────────────────


def test_payoff_normal() -> None:
    assert compute_payoff_ratio(0.8, 0.4) == 2.0


def test_payoff_equal() -> None:
    assert compute_payoff_ratio(0.5, 0.5) == 1.0


def test_payoff_zero_effort() -> None:
    assert compute_payoff_ratio(0.5, 0.0) == 0.0


def test_payoff_high_effort() -> None:
    assert compute_payoff_ratio(0.2, 0.8) == 0.25


# ── build_debt_report tests ────────────────────────────────────────


def test_build_schema() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS)
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["kind"] == KIND
    assert "generated_at" in doc


def test_build_project_name() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS, project_name="TestProject")
    assert doc["project_name"] == "TestProject"


def test_build_item_count() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS)
    assert len(doc["items"]) == 5


def test_build_sorted_by_payoff_desc() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS)
    ratios = [d["payoff_ratio"] for d in doc["items"]]
    assert ratios == sorted(ratios, reverse=True)


def test_build_payoff_calculated() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS)
    dep_item = next(d for d in doc["items"] if d["title"] == "Deprecated requests library version")
    assert dep_item["payoff_ratio"] == 4.0  # 0.8 / 0.2


def test_build_categories() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS)
    by_cat = doc["by_category"]
    assert len(by_cat["code_complexity"]) == 2
    assert len(by_cat["test_coverage"]) == 1
    assert len(by_cat["deprecated_dependency"]) == 1
    assert len(by_cat["architecture"]) == 1


def test_build_severity_scores() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS)
    dep_item = next(d for d in doc["items"] if d["severity"] == "critical")
    assert dep_item["severity_score"] == 4


def test_build_summary() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS)
    summary = doc["summary"]
    assert summary["total_items"] == 5
    assert summary["by_severity"]["critical"] == 1
    assert summary["by_severity"]["high"] == 1
    assert summary["by_severity"]["medium"] == 2
    assert summary["by_severity"]["low"] == 1


def test_build_summary_category_counts() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS)
    by_cat = doc["summary"]["by_category"]
    assert by_cat["code_complexity"] == 2
    assert by_cat["architecture"] == 1


def test_build_invalid_category_defaults() -> None:
    items = [{"title": "X", "category": "invalid"}]
    doc = build_debt_report(items)
    assert doc["items"][0]["category"] == "code_complexity"


def test_build_clamps_scores() -> None:
    items = [{"title": "X", "impact": 1.5, "effort": -0.3}]
    doc = build_debt_report(items)
    item = doc["items"][0]
    assert item["impact"] == 1.0
    assert item["effort"] == 0.0


def test_build_empty() -> None:
    doc = build_debt_report([])
    assert doc["items"] == []
    assert doc["summary"]["total_items"] == 0


# ── Markdown rendering ──────────────────────────────────────────────


def test_render_markdown_title() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS, project_name="TestApp")
    md = render_debt_markdown(doc)
    assert "# Technical Debt Report — TestApp" in md


def test_render_markdown_summary() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS)
    md = render_debt_markdown(doc)
    assert "Total debt items: 5" in md


def test_render_markdown_severity_breakdown() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS)
    md = render_debt_markdown(doc)
    assert "### By Severity" in md
    assert "**Critical**: 1" in md


def test_render_markdown_prioritized_items() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS)
    md = render_debt_markdown(doc)
    assert "## Prioritized Debt Items" in md
    assert "payoff ratio" in md.lower()


def test_render_markdown_item_details() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS)
    md = render_debt_markdown(doc)
    assert "Monolithic auth module" in md
    assert "**Impact**:" in md
    assert "**Effort**:" in md
    assert "**Location**:" in md


def test_render_markdown_category_sections() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS)
    md = render_debt_markdown(doc)
    assert "## Code Complexity" in md
    assert "## Deprecated Dependencies" in md


# ── JSON rendering ──────────────────────────────────────────────────


def test_render_json_valid() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS)
    output = render_debt_json(doc)
    parsed = json.loads(output)
    assert parsed["schema_version"] == SCHEMA_VERSION


def test_render_json_roundtrip() -> None:
    doc = build_debt_report(SAMPLE_DEBT_ITEMS, project_name="App")
    output = render_debt_json(doc)
    parsed = json.loads(output)
    assert parsed["project_name"] == "App"
    assert len(parsed["items"]) == 5

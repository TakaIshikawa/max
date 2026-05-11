"""Tests for investment case export."""

from __future__ import annotations

import json

from max.exports import (
    build_investment_case,
    render_investment_case_json,
    render_investment_case_markdown,
)
from max.exports.investment_case import KIND, SCHEMA_VERSION


def _unit() -> dict:
    return {
        "id": "bu-invest-001",
        "title": "Revenue Recovery Console",
        "problem": "finance teams cannot find preventable revenue leakage quickly",
        "solution_approach": "a workflow console that prioritizes leakage fixes by account impact",
        "tech_stack": ["React", "FastAPI", "Postgres"],
        "signals": [
            {
                "id": "sig-1",
                "title": "CFO demand for leakage reporting",
                "summary": "Revenue operations teams report growth demand for automated recovery workflows.",
                "source": "interview",
                "url": "https://example.com/sig-1",
                "competitors": ["spreadsheet workflow"],
            },
            {
                "id": "sig-2",
                "title": "Expansion market signal",
                "content": "Analyst note shows adoption growth in revenue intelligence tooling.",
                "source": "analyst",
                "url": "https://example.com/sig-2",
            },
        ],
        "metadata": {"team_size": 4, "estimated_timeline": "10 weeks"},
    }


def _evaluation(score: float = 84.0) -> dict:
    return {
        "overall_score": score,
        "recommendation": "yes" if score >= 75 else "maybe",
        "dimensions": {
            "market_demand": 8.8,
            "technical_complexity": 6.2,
            "strategic_fit": 8.5,
        },
    }


def test_build_investment_case_with_complete_data() -> None:
    case = build_investment_case(
        _unit(),
        _evaluation(),
        {
            "size_estimate": "$18M SOM",
            "growth_indicators": ["budget owner urgency", "category expansion"],
            "alternatives": ["manual spreadsheets", "BI dashboards"],
            "confidence": "high",
            "expected_outcomes": ["Revenue leakage recovered", "Analyst hours saved"],
        },
    )

    assert case["schema_version"] == SCHEMA_VERSION
    assert case["kind"] == KIND
    assert case["source"]["idea_id"] == "bu-invest-001"
    assert "Revenue Recovery Console" in case["executive_summary"]
    assert case["problem_validation"]["source_count"] == 2
    assert case["proposed_solution"]["tech_stack"] == ["FastAPI", "Postgres", "React"]
    assert case["market_opportunity"]["size_estimate"] == "$18M SOM"
    assert case["competitive_landscape"]["alternatives"] == ["manual spreadsheets", "BI dashboards"]
    assert case["resource_requirements"]["team_size"] == 4
    assert case["recommendation"]["decision"] == "go"
    assert len(case["risk_factors"]) <= 3
    assert case["evidence_chain"][0]["url"] == "https://example.com/sig-1"
    assert case["expected_outcomes"][0]["kpi"] == "Revenue leakage recovered"


def test_build_investment_case_with_minimal_data_without_market_data() -> None:
    case = build_investment_case(
        {
            "id": "bu-min",
            "title": "Internal Tooling",
            "solution": {"approach": "automate repetitive triage", "suggested_stack": {"backend": "FastAPI"}},
        },
        {"overall_score": 62, "dimensions": {"market_demand": 5.1}},
    )

    assert case["source"]["idea_id"] == "bu-min"
    assert case["problem_validation"]["source_count"] == 0
    assert case["market_opportunity"]["size_estimate"] == "Unknown; market sizing data not provided"
    assert case["market_opportunity"]["confidence"] == "low"
    assert case["proposed_solution"]["solution_approach"] == "automate repetitive triage"
    assert case["recommendation"]["decision"] == "conditional"
    assert case["evidence_chain"] == []


def test_recommendation_logic_for_go_conditional_and_no_go() -> None:
    assert build_investment_case(_unit(), _evaluation(82))["recommendation"]["decision"] == "go"
    assert build_investment_case(_unit(), _evaluation(64))["recommendation"]["decision"] == "conditional"
    assert build_investment_case(_unit(), {"overall_score": 42, "recommendation": "no"})["recommendation"]["decision"] == "no-go"


def test_markdown_and_json_renderers_are_stable() -> None:
    case = build_investment_case(_unit(), _evaluation())
    markdown = render_investment_case_markdown(case)
    rendered_json = render_investment_case_json(case)
    payload = json.loads(rendered_json)

    assert markdown.startswith("# Investment Case")
    assert "## Recommendation" in markdown
    assert "## Evidence Chain" in markdown
    assert payload["kind"] == KIND
    assert payload["recommendation"]["decision"] == "go"
    assert json.loads(json.dumps(payload)) == payload

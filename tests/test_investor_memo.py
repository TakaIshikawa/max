"""Tests for investor memo export module."""

from __future__ import annotations

import json

import pytest

from max.exports.investor_memo import (
    build_investor_memo,
    render_investor_memo_json,
    render_investor_memo_markdown,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def full_report() -> dict:
    return build_investor_memo(
        company_name="Acme Corp",
        tagline="AI-powered signal intelligence",
        market_opportunity={
            "tam": 10_000_000_000,
            "sam": 2_000_000_000,
            "som": 200_000_000,
            "description": "The global market intelligence market.",
        },
        competitive_landscape=[
            {
                "name": "CompetitorA",
                "description": "Legacy analytics platform",
                "differentiator": "We offer real-time analysis",
            },
            {
                "name": "CompetitorB",
                "description": "Niche player in vertical",
            },
        ],
        traction={
            "mrr": 50_000,
            "arr": 600_000,
            "customers": 120,
            "growth_rate": 0.15,
        },
        team=[
            {"name": "Alice", "role": "CEO", "bio": "Ex-Google"},
            {"name": "Bob", "role": "CTO"},
        ],
        ask_amount=5_000_000,
        use_of_funds=[
            {"category": "Engineering", "percentage": 50},
            {"category": "Sales & Marketing", "percentage": 30},
            {"category": "Operations", "percentage": 20},
        ],
    )


# ── Schema / metadata ───────────────────────────────────────────────


def test_schema_metadata(full_report: dict) -> None:
    assert full_report["schema_version"] == "max.investor_memo.v1"
    assert full_report["kind"] == "max.investor_memo"
    assert "generated_at" in full_report


def test_company_name(full_report: dict) -> None:
    assert full_report["company_name"] == "Acme Corp"


# ── Executive summary ───────────────────────────────────────────────


def test_executive_summary_generated(full_report: dict) -> None:
    es = full_report["executive_summary"]
    assert "text" in es
    assert "Acme Corp" in es["text"]


def test_executive_summary_includes_traction(full_report: dict) -> None:
    es = full_report["executive_summary"]
    assert "MRR" in es["text"]
    assert "customers" in es["text"]


def test_executive_summary_includes_ask(full_report: dict) -> None:
    es = full_report["executive_summary"]
    assert "5,000,000" in es["text"]


def test_executive_summary_minimal() -> None:
    report = build_investor_memo(company_name="X")
    es = report["executive_summary"]
    assert "X" in es["text"]


# ── Market opportunity ───────────────────────────────────────────────


def test_market_opportunity_values(full_report: dict) -> None:
    mkt = full_report["market_opportunity"]
    assert mkt["tam"] == 10_000_000_000
    assert mkt["sam"] == 2_000_000_000
    assert mkt["som"] == 200_000_000


def test_market_opportunity_defaults() -> None:
    report = build_investor_memo(company_name="X")
    mkt = report["market_opportunity"]
    assert mkt["tam"] is None
    assert mkt["sam"] is None


# ── Competitive landscape ───────────────────────────────────────────


def test_competitors_listed(full_report: dict) -> None:
    comps = full_report["competitive_landscape"]
    assert len(comps) == 2
    assert comps[0]["name"] == "CompetitorA"
    assert comps[0]["differentiator"] == "We offer real-time analysis"


def test_no_competitors() -> None:
    report = build_investor_memo(company_name="X")
    assert report["competitive_landscape"] == []


# ── Traction ─────────────────────────────────────────────────────────


def test_traction_metrics(full_report: dict) -> None:
    tr = full_report["traction"]
    assert tr["metrics"]["mrr"] == 50_000
    assert tr["metrics"]["customers"] == 120


def test_traction_defaults_empty() -> None:
    report = build_investor_memo(company_name="X")
    assert report["traction"]["metrics"] == {}


# ── Team ─────────────────────────────────────────────────────────────


def test_team_members(full_report: dict) -> None:
    team = full_report["team"]
    assert len(team) == 2
    assert team[0]["name"] == "Alice"
    assert team[0]["role"] == "CEO"
    assert team[0]["bio"] == "Ex-Google"


def test_team_defaults_empty() -> None:
    report = build_investor_memo(company_name="X")
    assert report["team"] == []


# ── Funding ──────────────────────────────────────────────────────────


def test_ask_amount(full_report: dict) -> None:
    fd = full_report["funding"]
    assert fd["ask_amount"] == 5_000_000


def test_use_of_funds_breakdown(full_report: dict) -> None:
    fd = full_report["funding"]
    assert len(fd["use_of_funds"]) == 3
    total = sum(item["percentage"] for item in fd["use_of_funds"])
    assert total == 100


def test_funding_defaults_none() -> None:
    report = build_investor_memo(company_name="X")
    fd = report["funding"]
    assert fd["ask_amount"] is None
    assert fd["use_of_funds"] == []


# ── Rendering ────────────────────────────────────────────────────────


def test_render_markdown_sections(full_report: dict) -> None:
    md = render_investor_memo_markdown(full_report)
    assert "# Investor Memo:" in md
    assert "## Executive Summary" in md
    assert "## Market Opportunity" in md
    assert "## Competitive Landscape" in md
    assert "## Traction" in md
    assert "## Team" in md
    assert "## The Ask" in md


def test_render_markdown_ends_with_newline(full_report: dict) -> None:
    md = render_investor_memo_markdown(full_report)
    assert md.endswith("\n")
    assert not md.endswith("\n\n")


def test_render_json_valid(full_report: dict) -> None:
    raw = render_investor_memo_json(full_report)
    parsed = json.loads(raw)
    assert parsed["schema_version"] == "max.investor_memo.v1"


# ── Validation ───────────────────────────────────────────────────────


def test_empty_company_name_rejected() -> None:
    with pytest.raises(ValueError, match="company_name"):
        build_investor_memo(company_name="")


def test_use_of_funds_must_sum_to_100() -> None:
    with pytest.raises(ValueError, match="sum to 100"):
        build_investor_memo(
            company_name="X",
            use_of_funds=[
                {"category": "Eng", "percentage": 50},
                {"category": "Sales", "percentage": 30},
            ],
        )

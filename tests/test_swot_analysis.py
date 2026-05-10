"""Tests for SWOT analysis export module."""

from __future__ import annotations

import json

import pytest

from max.exports.swot_analysis import (
    build_swot_analysis,
    render_swot_analysis_json,
    render_swot_analysis_markdown,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def full_report() -> dict:
    return build_swot_analysis(
        subject="MaxSignal Platform",
        strengths=[
            {"description": "Strong technical team", "impact": 5, "implication": "Fast iteration", "action": "Hire more senior engineers"},
            {"description": "Unique dataset", "impact": 4},
        ],
        weaknesses=[
            {"description": "Limited brand awareness", "impact": 3, "action": "Invest in marketing"},
        ],
        opportunities=[
            {"description": "Growing market demand", "impact": 5, "implication": "Expand TAM"},
            {"description": "Competitor exit", "impact": 4},
        ],
        threats=[
            {"description": "Regulatory changes", "impact": 2},
            {"description": "New entrant with funding", "impact": 4, "action": "Accelerate roadmap"},
        ],
    )


# ── Schema / metadata ───────────────────────────────────────────────


def test_schema_metadata(full_report: dict) -> None:
    assert full_report["schema_version"] == "max.swot_analysis.v1"
    assert full_report["kind"] == "max.swot_analysis"
    assert "generated_at" in full_report
    assert full_report["subject"] == "MaxSignal Platform"


# ── Four-quadrant structure ──────────────────────────────────────────


def test_all_quadrants_present(full_report: dict) -> None:
    quads = full_report["quadrants"]
    assert "strengths" in quads
    assert "weaknesses" in quads
    assert "opportunities" in quads
    assert "threats" in quads


def test_strengths_count(full_report: dict) -> None:
    assert len(full_report["quadrants"]["strengths"]) == 2


def test_weaknesses_count(full_report: dict) -> None:
    assert len(full_report["quadrants"]["weaknesses"]) == 1


def test_opportunities_count(full_report: dict) -> None:
    assert len(full_report["quadrants"]["opportunities"]) == 2


def test_threats_count(full_report: dict) -> None:
    assert len(full_report["quadrants"]["threats"]) == 2


# ── Strategic implications and actions ───────────────────────────────


def test_implication_preserved(full_report: dict) -> None:
    s = full_report["quadrants"]["strengths"]
    top = s[0]  # Sorted by impact, so impact=5 is first
    assert top["implication"] == "Fast iteration"


def test_action_preserved(full_report: dict) -> None:
    w = full_report["quadrants"]["weaknesses"]
    assert w[0]["action"] == "Invest in marketing"


def test_missing_implication_defaults_empty() -> None:
    report = build_swot_analysis(
        subject="X",
        strengths=[{"description": "Good team"}],
    )
    s = report["quadrants"]["strengths"][0]
    assert s["implication"] == ""


def test_missing_action_defaults_empty() -> None:
    report = build_swot_analysis(
        subject="X",
        threats=[{"description": "Risk"}],
    )
    t = report["quadrants"]["threats"][0]
    assert t["action"] == ""


# ── Weighted scoring ────────────────────────────────────────────────


def test_items_sorted_by_impact_descending(full_report: dict) -> None:
    strengths = full_report["quadrants"]["strengths"]
    assert strengths[0]["impact"] == 5
    assert strengths[1]["impact"] == 4


def test_default_impact_is_three() -> None:
    report = build_swot_analysis(
        subject="X",
        strengths=[{"description": "No impact specified"}],
    )
    assert report["quadrants"]["strengths"][0]["impact"] == 3


def test_summary_scores(full_report: dict) -> None:
    ss = full_report["summary_scores"]
    # Strengths: 5 + 4 = 9
    assert ss["strengths_total"] == 9.0
    # Weaknesses: 3
    assert ss["weaknesses_total"] == 3.0
    # Opportunities: 5 + 4 = 9
    assert ss["opportunities_total"] == 9.0
    # Threats: 2 + 4 = 6
    assert ss["threats_total"] == 6.0


def test_internal_balance(full_report: dict) -> None:
    ss = full_report["summary_scores"]
    assert ss["internal_balance"] == 9.0 - 3.0


def test_external_balance(full_report: dict) -> None:
    ss = full_report["summary_scores"]
    assert ss["external_balance"] == 9.0 - 6.0


def test_empty_quadrants_score_zero() -> None:
    report = build_swot_analysis(subject="X")
    ss = report["summary_scores"]
    assert ss["strengths_total"] == 0.0
    assert ss["internal_balance"] == 0.0
    assert ss["external_balance"] == 0.0


# ── Rendering ────────────────────────────────────────────────────────


def test_render_markdown_sections(full_report: dict) -> None:
    md = render_swot_analysis_markdown(full_report)
    assert "# SWOT Analysis:" in md
    assert "## Strengths" in md
    assert "## Weaknesses" in md
    assert "## Opportunities" in md
    assert "## Threats" in md
    assert "## Summary Scores" in md


def test_render_markdown_shows_impact_scores(full_report: dict) -> None:
    md = render_swot_analysis_markdown(full_report)
    assert "[5/5]" in md
    assert "[4/5]" in md


def test_render_markdown_ends_with_newline(full_report: dict) -> None:
    md = render_swot_analysis_markdown(full_report)
    assert md.endswith("\n")
    assert not md.endswith("\n\n")


def test_render_json_valid(full_report: dict) -> None:
    raw = render_swot_analysis_json(full_report)
    parsed = json.loads(raw)
    assert parsed["schema_version"] == "max.swot_analysis.v1"


# ── Validation / edge cases ──────────────────────────────────────────


def test_empty_subject_rejected() -> None:
    with pytest.raises(ValueError, match="subject"):
        build_swot_analysis(subject="")


def test_invalid_impact_rejected() -> None:
    with pytest.raises(ValueError, match="impact"):
        build_swot_analysis(
            subject="X",
            strengths=[{"description": "Bad", "impact": 10}],
        )


def test_impact_zero_rejected() -> None:
    with pytest.raises(ValueError, match="impact"):
        build_swot_analysis(
            subject="X",
            weaknesses=[{"description": "Bad", "impact": 0}],
        )


def test_missing_description_rejected() -> None:
    with pytest.raises(ValueError, match="description"):
        build_swot_analysis(
            subject="X",
            strengths=[{"impact": 3}],
        )


def test_all_empty_quadrants() -> None:
    report = build_swot_analysis(subject="X")
    for quad in ("strengths", "weaknesses", "opportunities", "threats"):
        assert report["quadrants"][quad] == []

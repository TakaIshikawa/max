from __future__ import annotations

from max.analysis.portfolio_segment_gap_map import (
    build_portfolio_segment_gap_map,
    render_portfolio_segment_gap_map_markdown,
)


def test_portfolio_segment_gap_map_counts_configured_combinations() -> None:
    report = build_portfolio_segment_gap_map(
        [
            {"segment": "smb", "lifecycle_stage": "trial", "problem_category": "activation"},
            {"segment": "smb", "lifecycle_stage": "trial", "problem_category": "activation"},
            {"segment": "enterprise", "lifecycle_stage": "renewal", "problem_category": "security"},
        ],
        target_segments=["smb", "enterprise"],
        lifecycle_stages=["trial", "renewal"],
        problem_categories=["activation", "security"],
        min_coverage=1,
        max_coverage=2,
    )

    assert report["schema_version"] == "max.portfolio_segment_gap_map.v1"
    assert report["kind"] == "max.portfolio_segment_gap_map"
    assert report["summary"]["combination_count"] == 8
    rows = {(row["segment"], row["lifecycle_stage"], row["problem_category"]): row for row in report["coverage_rows"]}
    assert rows[("smb", "trial", "activation")]["coverage_count"] == 2
    assert rows[("enterprise", "renewal", "security")]["coverage_status"] == "balanced"
    assert rows[("enterprise", "trial", "activation")]["coverage_status"] == "gap"


def test_portfolio_segment_gap_map_identifies_gap_saturation_and_balanced() -> None:
    report = build_portfolio_segment_gap_map(
        [
            {"segment": "smb", "lifecycle_stage": "trial", "problem_category": "activation"},
            {"segment": "smb", "lifecycle_stage": "trial", "problem_category": "activation"},
            {"segment": "smb", "lifecycle_stage": "trial", "problem_category": "activation"},
            {"segment": "enterprise", "lifecycle_stage": "trial", "problem_category": "security"},
        ],
        target_segments=["smb", "enterprise"],
        lifecycle_stages=["trial"],
        problem_categories=["activation", "security"],
        min_coverage=1,
        max_coverage=2,
    )

    statuses = {row["coverage_status"] for row in report["coverage_rows"]}
    assert statuses == {"gap", "balanced", "saturation_risk"}
    assert report["coverage_rows"][0]["coverage_status"] == "gap"
    assert "create 1 idea(s)" in report["coverage_rows"][0]["suggested_ideation_focus"]


def test_portfolio_segment_gap_map_supports_multi_value_items() -> None:
    report = build_portfolio_segment_gap_map(
        [
            {
                "segment": ["smb", "midmarket"],
                "stage": "onboarding",
                "category": ["integration", "training"],
            }
        ],
        target_segments=["midmarket", "smb"],
        lifecycle_stages=["onboarding"],
        problem_categories=["integration", "training"],
    )

    assert all(row["coverage_count"] == 1 for row in report["coverage_rows"])


def test_portfolio_segment_gap_map_markdown_includes_underserved_and_focus() -> None:
    report = build_portfolio_segment_gap_map(
        [{"segment": "smb", "lifecycle_stage": "trial", "problem_category": "activation"}],
        target_segments=["enterprise", "smb"],
        lifecycle_stages=["trial"],
        problem_categories=["activation"],
        min_coverage=1,
        max_coverage=2,
    )

    first = render_portfolio_segment_gap_map_markdown(report)
    second = render_portfolio_segment_gap_map_markdown(report)

    assert first == second
    assert first.startswith("# Portfolio Segment Gap Map")
    assert "## Most Underserved Combinations" in first
    assert "enterprise / trial / activation" in first
    assert "- Suggested ideation focus:" in first

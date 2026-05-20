from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.profile_signal_mix_recommendations import (
    KIND,
    SCHEMA_VERSION,
    ProfileSignalMixObservation,
    build_profile_signal_mix_recommendations,
    render_profile_signal_mix_recommendations,
)


def test_profile_signal_mix_recommendations_combines_volume_quality_approval_and_minimum_share() -> None:
    report = build_profile_signal_mix_recommendations(_observations(), default_minimum_share=0.2)
    repeated = build_profile_signal_mix_recommendations(_observations(), default_minimum_share=0.2)

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"]["profile_count"] == 2
    assert report["summary"]["source_count"] == 5
    assert report["summary"]["increase_count"] == 1
    assert report["summary"]["decrease_count"] == 1
    assert report["summary"]["hold_count"] == 1
    assert report["summary"]["investigate_count"] == 2
    assert [row["recommendation"] for row in report["recommendations"]] == [
        "increase",
        "investigate",
        "investigate",
        "decrease",
        "hold",
    ]

    rows = {(row["profile"], row["source"]): row for row in report["recommendations"]}
    increase = rows[("devtools", "github")]
    assert increase["observed_volume"] == 10
    assert increase["observed_share"] == 0.1429
    assert increase["approval_share"] == 0.4
    assert increase["minimum_share"] == 0.2
    assert increase["quality_score"] == 0.75
    assert increase["recommendation"] == "increase"
    assert increase["reasons"] == [
        "Observed share is below the configured minimum.",
        "Approval contribution outpaces observed signal share.",
        "Quality score is strong.",
    ]

    investigate = rows[("security", "nvd")]
    assert investigate["recommendation"] == "investigate"
    assert investigate["reasons"] == ["No observed signal volume for a configured source floor."]

    weak_floor = rows[("devtools", "stackoverflow")]
    assert weak_floor["recommendation"] == "investigate"
    assert weak_floor["reasons"] == ["Observed share is below the configured minimum and quality is weak."]

    decrease = rows[("devtools", "hackernews")]
    assert decrease["recommendation"] == "decrease"
    assert decrease["approval_share"] == 0.1

    hold = rows[("security", "cisa_kev")]
    assert hold["recommendation"] == "hold"
    assert hold["priority"] == 3
    assert report["summary"]["top_opportunities"][0]["source"] == "github"


def test_profile_signal_mix_recommendations_accepts_mapping_rows_and_empty_input() -> None:
    report = build_profile_signal_mix_recommendations(
        [
            {
                "profile": "ops",
                "source_adapter": "reddit",
                "signal_count": 4,
                "quality_score": 0.7,
                "approval_contribution": 3,
                "minimum_share": 0.1,
            }
        ]
    )

    assert report["recommendations"][0]["profile"] == "ops"
    assert report["recommendations"][0]["source"] == "reddit"
    assert report["recommendations"][0]["recommendation"] == "hold"

    empty = build_profile_signal_mix_recommendations([])
    assert empty["summary"]["profile_count"] == 0
    assert empty["summary"]["top_opportunities"] == []
    assert empty["recommendations"] == []


def test_render_profile_signal_mix_recommendations_json_markdown_csv_and_invalid_format() -> None:
    report = build_profile_signal_mix_recommendations(_observations(), default_minimum_share=0.2)

    assert json.loads(render_profile_signal_mix_recommendations(report, fmt="json")) == report

    markdown = render_profile_signal_mix_recommendations(report, fmt="markdown")
    assert markdown.startswith("# Profile Signal Mix Recommendations")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert markdown.index("| `devtools` | `github` | increase |") < markdown.index(
        "| `devtools` | `hackernews` | decrease |"
    )
    assert "## Top Opportunities" in markdown
    assert "- `devtools` / `github`: increase" in markdown

    rendered_csv = render_profile_signal_mix_recommendations(report, fmt="csv")
    assert rendered_csv.splitlines()[0] == (
        "profile,source,recommendation,priority,observed_volume,observed_share,"
        "quality_score,approval_contribution,approval_share,minimum_share,opportunity_score,reasons"
    )
    rows = list(csv.DictReader(StringIO(rendered_csv)))
    assert rows[0]["source"] == "github"
    assert rows[0]["recommendation"] == "increase"
    assert "Approval contribution outpaces observed signal share." in rows[0]["reasons"]

    with pytest.raises(ValueError, match="Unsupported profile signal mix recommendations format: yaml"):
        render_profile_signal_mix_recommendations(report, fmt="yaml")


def test_profile_signal_mix_recommendations_validates_arguments() -> None:
    with pytest.raises(ValueError, match="default_minimum_share must be between 0 and 1"):
        build_profile_signal_mix_recommendations([], default_minimum_share=1.1)
    with pytest.raises(ValueError, match="low_quality_threshold must be between 0 and 1"):
        build_profile_signal_mix_recommendations([], low_quality_threshold=-0.1)
    with pytest.raises(ValueError, match="strong_quality_threshold must be between 0 and 1"):
        build_profile_signal_mix_recommendations([], strong_quality_threshold=1.1)
    with pytest.raises(ValueError, match="approval_gap_threshold must be non-negative"):
        build_profile_signal_mix_recommendations([], approval_gap_threshold=-0.1)
    with pytest.raises(ValueError, match="top_opportunity_limit must be at least 1"):
        build_profile_signal_mix_recommendations([], top_opportunity_limit=0)
    with pytest.raises(ValueError, match="observed_volume must be non-negative"):
        build_profile_signal_mix_recommendations(
            [ProfileSignalMixObservation("devtools", "bad", -1, 0.5, 0.0)]
        )


def _observations() -> list[ProfileSignalMixObservation]:
    return [
        ProfileSignalMixObservation(
            profile="devtools",
            source="hackernews",
            observed_volume=50,
            quality_score=0.25,
            approval_contribution=1,
            minimum_share=0.2,
        ),
        ProfileSignalMixObservation(
            profile="devtools",
            source="github",
            observed_volume=10,
            quality_score=0.75,
            approval_contribution=4,
            minimum_share=0.2,
        ),
        ProfileSignalMixObservation(
            profile="devtools",
            source="stackoverflow",
            observed_volume=10,
            quality_score=0.2,
            approval_contribution=5,
            minimum_share=0.2,
        ),
        ProfileSignalMixObservation(
            profile="security",
            source="nvd",
            observed_volume=0,
            quality_score=0.4,
            approval_contribution=0,
            minimum_share=0.25,
        ),
        ProfileSignalMixObservation(
            profile="security",
            source="cisa_kev",
            observed_volume=8,
            quality_score=0.65,
            approval_contribution=2,
            minimum_share=0.25,
        ),
    ]

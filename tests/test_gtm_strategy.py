"""Tests for go-to-market strategy export module."""

from __future__ import annotations

import json

import pytest

from max.exports.gtm_strategy import (
    build_gtm_strategy,
    render_gtm_strategy_json,
    render_gtm_strategy_markdown,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def segments() -> list[dict]:
    return [
        {"name": "Enterprise", "description": "Large organizations with 500+ employees", "priority": 1},
        {"name": "SMB", "description": "Small and medium businesses", "priority": 2},
        {"name": "Developers", "description": "Individual developers and hobbyists", "priority": 3},
    ]


@pytest.fixture
def basic_report(segments: list[dict]) -> dict:
    return build_gtm_strategy(
        product_name="MaxSignal",
        target_segments=segments,
    )


# ── Schema / metadata ───────────────────────────────────────────────


def test_schema_metadata(basic_report: dict) -> None:
    assert basic_report["schema_version"] == "max.gtm_strategy.v1"
    assert basic_report["kind"] == "max.gtm_strategy"
    assert "generated_at" in basic_report
    assert basic_report["source"]["entity_type"] == "gtm_strategy"


def test_product_name_stored(basic_report: dict) -> None:
    assert basic_report["product_name"] == "MaxSignal"


# ── Positioning ──────────────────────────────────────────────────────


def test_default_positioning(basic_report: dict) -> None:
    pos = basic_report["positioning"]
    assert "statement" in pos
    assert "differentiator" in pos
    assert "value_proposition" in pos
    assert "MaxSignal" in pos["statement"]


def test_custom_positioning(segments: list[dict]) -> None:
    report = build_gtm_strategy(
        product_name="MaxSignal",
        target_segments=segments,
        positioning={
            "statement": "The best signal intelligence platform.",
            "differentiator": "Real-time analysis.",
            "value_proposition": "Save 10 hours per week.",
        },
    )
    pos = report["positioning"]
    assert pos["statement"] == "The best signal intelligence platform."
    assert pos["differentiator"] == "Real-time analysis."
    assert pos["value_proposition"] == "Save 10 hours per week."


# ── Target segment prioritization ───────────────────────────────────


def test_segments_sorted_by_priority(basic_report: dict) -> None:
    segs = basic_report["target_segments"]
    assert segs[0]["name"] == "Enterprise"
    assert segs[1]["name"] == "SMB"
    assert segs[2]["name"] == "Developers"


def test_segment_priority_default() -> None:
    report = build_gtm_strategy(
        product_name="X",
        target_segments=[
            {"name": "A", "description": "Segment A"},
            {"name": "B", "description": "Segment B", "priority": 1},
        ],
    )
    segs = report["target_segments"]
    # B has priority 1, A defaults to 3
    assert segs[0]["name"] == "B"
    assert segs[1]["name"] == "A"
    assert segs[1]["priority"] == 3


def test_segment_rationale_preserved() -> None:
    report = build_gtm_strategy(
        product_name="X",
        target_segments=[
            {"name": "A", "description": "D", "rationale": "High TAM"},
        ],
    )
    assert report["target_segments"][0]["rationale"] == "High TAM"


# ── Channel plan ─────────────────────────────────────────────────────


def test_default_channels_returned(basic_report: dict) -> None:
    channels = basic_report["channel_plan"]
    assert len(channels) > 0
    names = [ch["name"] for ch in channels]
    assert "Content Marketing" in names


def test_custom_channel_filter(segments: list[dict]) -> None:
    report = build_gtm_strategy(
        product_name="X",
        target_segments=segments,
        channels=["Content Marketing", "Product-Led Growth"],
    )
    names = [ch["name"] for ch in report["channel_plan"]]
    assert names == ["Content Marketing", "Product-Led Growth"]


def test_unknown_channel_gets_custom_category(segments: list[dict]) -> None:
    report = build_gtm_strategy(
        product_name="X",
        target_segments=segments,
        channels=["Carrier Pigeon"],
    )
    ch = report["channel_plan"][0]
    assert ch["name"] == "Carrier Pigeon"
    assert ch["category"] == "custom"


def test_channel_has_required_fields(basic_report: dict) -> None:
    for ch in basic_report["channel_plan"]:
        assert "name" in ch
        assert "category" in ch
        assert "effort" in ch
        assert "cost" in ch


# ── Launch timeline ──────────────────────────────────────────────────


def test_timeline_with_date_and_milestones(segments: list[dict]) -> None:
    report = build_gtm_strategy(
        product_name="X",
        target_segments=segments,
        launch_date="2026-09-01",
        milestones=[
            {"name": "Beta", "date": "2026-07-01"},
            {"name": "GA", "date": "2026-09-01"},
        ],
    )
    tl = report["timeline"]
    assert tl["launch_date"] == "2026-09-01"
    assert len(tl["milestones"]) == 2
    assert tl["milestones"][0]["name"] == "Beta"


def test_timeline_defaults_empty(basic_report: dict) -> None:
    tl = basic_report["timeline"]
    assert tl["launch_date"] is None
    assert tl["milestones"] == []


# ── Messaging framework ─────────────────────────────────────────────


def test_messaging_per_segment(basic_report: dict) -> None:
    msgs = basic_report["messaging_framework"]
    seg_names = [s["name"] for s in basic_report["target_segments"]]
    msg_segments = [m["segment"] for m in msgs]
    assert msg_segments == seg_names


def test_messaging_includes_product_name(basic_report: dict) -> None:
    for msg in basic_report["messaging_framework"]:
        assert "MaxSignal" in msg["headline"]


def test_messaging_has_required_fields(basic_report: dict) -> None:
    for msg in basic_report["messaging_framework"]:
        assert "segment" in msg
        assert "headline" in msg
        assert "key_message" in msg


# ── Rendering ────────────────────────────────────────────────────────


def test_render_markdown_sections(basic_report: dict) -> None:
    md = render_gtm_strategy_markdown(basic_report)
    assert "# Go-to-Market Strategy:" in md
    assert "## Positioning" in md
    assert "## Target Segments" in md
    assert "## Distribution Channels" in md
    assert "## Messaging Framework" in md


def test_render_markdown_ends_with_newline(basic_report: dict) -> None:
    md = render_gtm_strategy_markdown(basic_report)
    assert md.endswith("\n")
    assert not md.endswith("\n\n")


def test_render_json_valid(basic_report: dict) -> None:
    raw = render_gtm_strategy_json(basic_report)
    parsed = json.loads(raw)
    assert parsed["schema_version"] == "max.gtm_strategy.v1"


# ── Validation / edge cases ──────────────────────────────────────────


def test_empty_product_name_rejected() -> None:
    with pytest.raises(ValueError, match="product_name"):
        build_gtm_strategy(
            product_name="",
            target_segments=[{"name": "A", "description": "B"}],
        )


def test_empty_segments_rejected() -> None:
    with pytest.raises(ValueError, match="target_segments"):
        build_gtm_strategy(product_name="X", target_segments=[])


def test_segment_missing_name_rejected() -> None:
    with pytest.raises(ValueError, match="name"):
        build_gtm_strategy(
            product_name="X",
            target_segments=[{"description": "No name"}],
        )


def test_segment_missing_description_rejected() -> None:
    with pytest.raises(ValueError, match="description"):
        build_gtm_strategy(
            product_name="X",
            target_segments=[{"name": "A"}],
        )

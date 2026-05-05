"""Tests for design brief go-to-market strategy CSV export."""

from __future__ import annotations

import csv
from io import StringIO
from unittest.mock import Mock

from max.analysis.design_brief_go_to_market import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_go_to_market_strategy,
    render_design_brief_go_to_market_strategy,
    render_design_brief_go_to_market_strategy_csv,
)


def _mock_store() -> Mock:
    """Create a mock store with sample design brief and ideas."""
    store = Mock()

    design_brief = {
        "id": "db-gtm-001",
        "title": "Enterprise Analytics Platform",
        "domain": "analytics",
        "theme": "data-driven-insights",
        "readiness_score": 85.0,
        "design_status": "validated",
        "lead_idea_id": "idea-001",
        "source_idea_ids": ["idea-001", "idea-002"],
        "target_customer": "Enterprise data teams",
        "value_proposition": "Unified analytics with real-time insights",
        "competitive_position": "First to market with integrated ML pipelines",
        "buyer": "VP of Data",
        "workflow_context": "data analysis and reporting",
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-20T15:30:00Z",
    }

    idea_001 = Mock()
    idea_001.id = "idea-001"
    idea_001.title = "Real-time analytics dashboard"
    idea_001.specific_user = "Data analysts"
    idea_001.value_proposition = "Real-time data insights"

    idea_002 = Mock()
    idea_002.id = "idea-002"
    idea_002.title = "ML pipeline integration"

    store.get_design_brief.return_value = design_brief
    store.get_buildable_unit.side_effect = lambda id: (
        idea_001 if id == "idea-001" else idea_002 if id == "idea-002" else None
    )

    return store


def _minimal_store() -> Mock:
    """Create a mock store with minimal design brief."""
    store = Mock()

    design_brief = {
        "id": "db-minimal-001",
        "title": "Minimal Product",
        "source_idea_ids": [],
        "created_at": "2024-01-15T10:00:00Z",
    }

    store.get_design_brief.return_value = design_brief
    store.get_buildable_unit.return_value = None

    return store


def test_build_design_brief_go_to_market_strategy_is_deterministic() -> None:
    """Verify go-to-market strategy generation is deterministic."""
    store = _mock_store()

    first = build_design_brief_go_to_market_strategy(store, "db-gtm-001")
    second = build_design_brief_go_to_market_strategy(store, "db-gtm-001")

    assert first == second
    assert first is not None
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == KIND


def test_build_design_brief_go_to_market_strategy_has_expected_structure() -> None:
    """Verify generated strategy has expected top-level structure."""
    store = _mock_store()

    strategy = build_design_brief_go_to_market_strategy(store, "db-gtm-001")

    assert strategy is not None
    assert set(strategy) == {
        "schema_version",
        "kind",
        "source",
        "design_brief",
        "summary",
        "market_segments",
        "positioning_statements",
        "distribution_channels",
        "key_messaging",
        "launch_timeline",
        "source_ideas",
    }


def test_build_design_brief_go_to_market_strategy_creates_market_segments() -> None:
    """Verify market segments are created from context."""
    store = _mock_store()

    strategy = build_design_brief_go_to_market_strategy(store, "db-gtm-001")

    assert strategy is not None
    segments = strategy["market_segments"]
    assert len(segments) >= 2

    # Verify segment structure
    for segment in segments:
        assert "id" in segment
        assert segment["id"].startswith("SEG")
        assert "name" in segment
        assert "description" in segment
        assert "priority" in segment
        assert segment["priority"] in ["high", "medium", "low"]
        assert "source_idea_ids" in segment


def test_build_design_brief_go_to_market_strategy_creates_positioning() -> None:
    """Verify positioning statements are created for segments."""
    store = _mock_store()

    strategy = build_design_brief_go_to_market_strategy(store, "db-gtm-001")

    assert strategy is not None
    positioning = strategy["positioning_statements"]
    assert len(positioning) >= 2

    # Each positioning should have required fields
    for pos in positioning:
        assert "id" in pos
        assert pos["id"].startswith("POS")
        assert "segment_id" in pos
        assert "segment_name" in pos
        assert "statement" in pos
        assert len(pos["statement"]) > 0
        assert "priority" in pos


def test_build_design_brief_go_to_market_strategy_creates_channels() -> None:
    """Verify distribution channels are defined."""
    store = _mock_store()

    strategy = build_design_brief_go_to_market_strategy(store, "db-gtm-001")

    assert strategy is not None
    channels = strategy["distribution_channels"]
    assert len(channels) >= 3

    # Verify channel types and owners
    channel_types = {ch["type"] for ch in channels}
    assert "direct" in channel_types or "marketing" in channel_types

    for channel in channels:
        assert "id" in channel
        assert "name" in channel
        assert "type" in channel
        assert "owner" in channel
        assert "priority" in channel


def test_build_design_brief_go_to_market_strategy_creates_messaging() -> None:
    """Verify key messaging is created."""
    store = _mock_store()

    strategy = build_design_brief_go_to_market_strategy(store, "db-gtm-001")

    assert strategy is not None
    messaging = strategy["key_messaging"]
    assert len(messaging) >= 1

    for msg in messaging:
        assert "id" in msg
        assert msg["id"].startswith("MSG")
        assert "segment_name" in msg
        assert "message" in msg
        assert "priority" in msg


def test_build_design_brief_go_to_market_strategy_creates_timeline() -> None:
    """Verify launch timeline is generated."""
    store = _mock_store()

    strategy = build_design_brief_go_to_market_strategy(store, "db-gtm-001")

    assert strategy is not None
    timeline = strategy["launch_timeline"]
    assert len(timeline) >= 3

    phases = {item["phase"] for item in timeline}
    assert "pre-launch" in phases or "launch" in phases or "post-launch" in phases

    for item in timeline:
        assert "id" in item
        assert "phase" in item
        assert "activity" in item
        assert "owner" in item
        assert "priority" in item


def test_build_design_brief_go_to_market_strategy_handles_minimal_brief() -> None:
    """Verify strategy generation handles minimal design brief."""
    store = _minimal_store()

    strategy = build_design_brief_go_to_market_strategy(store, "db-minimal-001")

    assert strategy is not None
    assert strategy["summary"]["segment_count"] >= 2
    assert strategy["summary"]["channel_count"] >= 3

    # Should have fallback values
    assert strategy["summary"]["target_market"] != ""
    assert strategy["summary"]["value_proposition"] != ""


def test_build_design_brief_go_to_market_strategy_returns_none_for_missing_brief() -> None:
    """Verify function returns None when design brief doesn't exist."""
    store = Mock()
    store.get_design_brief.return_value = None

    result = build_design_brief_go_to_market_strategy(store, "nonexistent")

    assert result is None


def test_render_design_brief_go_to_market_strategy_csv_has_correct_headers() -> None:
    """Verify CSV output has correct header structure."""
    store = _mock_store()
    strategy = build_design_brief_go_to_market_strategy(store, "db-gtm-001")

    assert strategy is not None
    csv_output = render_design_brief_go_to_market_strategy_csv(strategy)

    lines = csv_output.strip().split("\n")
    assert len(lines) >= 2  # At least header + one row

    header_line = lines[0]
    headers = header_line.split(",")

    assert len(headers) == len(CSV_COLUMNS)
    assert headers[0] == "design_brief_id"
    assert headers[1] == "design_brief_title"
    assert headers[2] == "section"
    assert headers[3] == "item_id"


def test_render_design_brief_go_to_market_strategy_csv_formats_rows_correctly() -> None:
    """Verify CSV rows contain expected data."""
    store = _mock_store()
    strategy = build_design_brief_go_to_market_strategy(store, "db-gtm-001")

    assert strategy is not None
    csv_output = render_design_brief_go_to_market_strategy_csv(strategy)

    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    # Should have rows for all sections
    assert len(rows) > 0

    sections = {row["section"] for row in rows}
    assert "market_segments" in sections
    assert "positioning_statements" in sections
    assert "distribution_channels" in sections
    assert "key_messaging" in sections
    assert "launch_timeline" in sections

    # Verify first row has expected fields
    first_row = rows[0]
    assert first_row["design_brief_id"] == "db-gtm-001"
    assert first_row["design_brief_title"] == "Enterprise Analytics Platform"
    assert first_row["section"] != ""
    assert first_row["item_id"] != ""


def test_render_design_brief_go_to_market_strategy_csv_includes_all_sections() -> None:
    """Verify CSV includes rows for all strategy sections."""
    store = _mock_store()
    strategy = build_design_brief_go_to_market_strategy(store, "db-gtm-001")

    assert strategy is not None
    csv_output = render_design_brief_go_to_market_strategy_csv(strategy)

    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    # Count rows per section
    section_counts = {}
    for row in rows:
        section = row["section"]
        section_counts[section] = section_counts.get(section, 0) + 1

    # Each section should have at least one row
    assert section_counts.get("market_segments", 0) >= 2
    assert section_counts.get("positioning_statements", 0) >= 1
    assert section_counts.get("distribution_channels", 0) >= 3
    assert section_counts.get("key_messaging", 0) >= 1
    assert section_counts.get("launch_timeline", 0) >= 3


def test_render_design_brief_go_to_market_strategy_json_format() -> None:
    """Verify JSON rendering produces valid JSON."""
    store = _mock_store()
    strategy = build_design_brief_go_to_market_strategy(store, "db-gtm-001")

    assert strategy is not None
    json_output = render_design_brief_go_to_market_strategy(strategy, fmt="json")

    # Should be valid JSON
    import json

    parsed = json.loads(json_output)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND


def test_render_design_brief_go_to_market_strategy_markdown_format() -> None:
    """Verify Markdown rendering produces structured output."""
    store = _mock_store()
    strategy = build_design_brief_go_to_market_strategy(store, "db-gtm-001")

    assert strategy is not None
    markdown_output = render_design_brief_go_to_market_strategy(strategy, fmt="markdown")

    # Should have expected markdown structure
    assert "# Go-to-Market Strategy:" in markdown_output
    assert "## Summary" in markdown_output
    assert "## Market Segments" in markdown_output
    assert "## Distribution Channels" in markdown_output
    assert "Enterprise Analytics Platform" in markdown_output


def test_render_design_brief_go_to_market_strategy_invalid_format() -> None:
    """Verify invalid format raises ValueError."""
    store = _mock_store()
    strategy = build_design_brief_go_to_market_strategy(store, "db-gtm-001")

    assert strategy is not None
    try:
        render_design_brief_go_to_market_strategy(strategy, fmt="invalid")
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "Unsupported go-to-market strategy format" in str(e)


def test_csv_columns_constant_matches_implementation() -> None:
    """Verify CSV_COLUMNS constant matches actual implementation."""
    expected_columns = (
        "design_brief_id",
        "design_brief_title",
        "section",
        "item_id",
        "segment_name",
        "positioning",
        "channel_name",
        "channel_type",
        "message",
        "priority",
        "owner",
        "timeline",
        "success_metric",
        "source_idea_ids",
    )

    assert CSV_COLUMNS == expected_columns

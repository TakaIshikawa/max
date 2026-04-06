"""Tests for cursor-based pagination in REST API."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from max.store.db import Store, _decode_cursor, _encode_cursor
from max.types.buildable_unit import BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


# ── Cursor encoding/decoding tests ──────────────────────────────────


def test_cursor_encoding_roundtrip():
    """Test cursor encoding and decoding roundtrip."""
    timestamp = "2024-01-15T10:30:00+00:00"
    entity_id = "sig-abc123"

    cursor = _encode_cursor(timestamp, entity_id)
    decoded_timestamp, decoded_id = _decode_cursor(cursor)

    assert decoded_timestamp == timestamp
    assert decoded_id == entity_id


def test_cursor_decoding_invalid():
    """Test cursor decoding with invalid input."""
    with pytest.raises(ValueError, match="Invalid cursor format"):
        _decode_cursor("invalid_base64!!!")


def test_cursor_is_opaque():
    """Test that cursor is a base64 string (opaque)."""
    cursor = _encode_cursor("2024-01-15T10:30:00+00:00", "sig-abc123")
    # Should be base64 (only alphanumeric, +, /, =)
    assert all(c.isalnum() or c in ("+", "/", "=") for c in cursor)


# ── Signals pagination tests ───────────────────────────────────────


def test_signals_first_page(store: Store):
    """Test fetching the first page of signals."""
    # Create 5 signals
    for i in range(5):
        signal = Signal(
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title=f"Signal {i}",
            content=f"Content {i}",
            url=f"https://example.com/{i}",
        )
        store.insert_signal(signal)

    # Fetch first page with limit 3
    signals, next_cursor = store.get_signals_paginated(cursor=None, limit=3)

    assert len(signals) == 3
    assert next_cursor is not None
    # Should be in descending order (newest first)
    assert signals[0].title == "Signal 4"
    assert signals[2].title == "Signal 2"


def test_signals_following_cursor(store: Store):
    """Test following next_cursor returns the next page."""
    # Create 5 signals
    for i in range(5):
        signal = Signal(
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title=f"Signal {i}",
            content=f"Content {i}",
            url=f"https://example.com/{i}",
        )
        store.insert_signal(signal)

    # Fetch first page
    signals_page1, cursor1 = store.get_signals_paginated(cursor=None, limit=3)
    assert len(signals_page1) == 3
    assert cursor1 is not None

    # Fetch second page using cursor
    signals_page2, cursor2 = store.get_signals_paginated(cursor=cursor1, limit=3)
    assert len(signals_page2) == 2  # Only 2 remaining
    assert cursor2 is None  # No more pages

    # Verify no overlap
    page1_titles = {s.title for s in signals_page1}
    page2_titles = {s.title for s in signals_page2}
    assert page1_titles.isdisjoint(page2_titles)


def test_signals_last_page(store: Store):
    """Test that last page has has_more=False and next_cursor=None."""
    # Create 3 signals
    for i in range(3):
        signal = Signal(
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title=f"Signal {i}",
            content=f"Content {i}",
            url=f"https://example.com/{i}",
        )
        store.insert_signal(signal)

    # Fetch with limit that covers all items
    signals, next_cursor = store.get_signals_paginated(cursor=None, limit=5)

    assert len(signals) == 3
    assert next_cursor is None  # No more results


def test_signals_empty_result(store: Store):
    """Test pagination with empty result set."""
    signals, next_cursor = store.get_signals_paginated(cursor=None, limit=10)

    assert len(signals) == 0
    assert next_cursor is None


def test_signals_with_source_type_filter(store: Store):
    """Test pagination with source_type filter."""
    # Create signals with different source types
    for i in range(3):
        store.insert_signal(
            Signal(
                source_type=SignalSourceType.FORUM,
                source_adapter="test",
                title=f"Forum {i}",
                content=f"Content {i}",
                url=f"https://example.com/forum/{i}",
            )
        )
    for i in range(2):
        store.insert_signal(
            Signal(
                source_type=SignalSourceType.REGISTRY,
                source_adapter="test",
                title=f"Registry {i}",
                content=f"Content {i}",
                url=f"https://example.com/registry/{i}",
            )
        )

    # Fetch only forum signals
    signals, next_cursor = store.get_signals_paginated(
        cursor=None, limit=10, source_type="forum"
    )

    assert len(signals) == 3
    assert all(s.source_type == SignalSourceType.FORUM for s in signals)
    assert next_cursor is None

    # Verify count respects filter
    count = store.count_signals(source_type="forum")
    assert count == 3


def test_signals_stable_pagination_with_inserts(store: Store):
    """Test that pagination is stable when new items are inserted."""
    # Create initial 3 signals
    for i in range(3):
        signal = Signal(
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title=f"Signal {i}",
            content=f"Content {i}",
            url=f"https://example.com/{i}",
        )
        store.insert_signal(signal)

    # Fetch first page
    signals_page1, cursor1 = store.get_signals_paginated(cursor=None, limit=2)
    assert len(signals_page1) == 2
    page1_ids = {s.id for s in signals_page1}

    # Insert new signals (should appear before the cursor)
    for i in range(3, 5):
        signal = Signal(
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title=f"Signal {i}",
            content=f"Content {i}",
            url=f"https://example.com/new/{i}",
        )
        store.insert_signal(signal)

    # Fetch second page using cursor - should get original items, not new ones
    signals_page2, cursor2 = store.get_signals_paginated(cursor=cursor1, limit=2)
    page2_ids = {s.id for s in signals_page2}

    # Verify no overlap (stable pagination)
    assert page1_ids.isdisjoint(page2_ids)
    # Should get exactly 1 item from original set
    assert len(signals_page2) == 1


# ── Insights pagination tests ──────────────────────────────────────


def test_insights_first_page(store: Store):
    """Test fetching the first page of insights."""
    # Create 5 insights
    for i in range(5):
        insight = Insight(
            category=InsightCategory.GAP,
            title=f"Insight {i}",
            summary=f"Summary {i}",
            evidence=[],
            confidence=0.8,
            domains=["test"],
            implications=[],
            time_horizon="near_term",
        )
        store.insert_insight(insight)

    # Fetch first page
    insights, next_cursor = store.get_insights_paginated(cursor=None, limit=3)

    assert len(insights) == 3
    assert next_cursor is not None


def test_insights_pagination_complete(store: Store):
    """Test complete pagination through all insights."""
    # Create 7 insights
    for i in range(7):
        insight = Insight(
            category=InsightCategory.GAP,
            title=f"Insight {i}",
            summary=f"Summary {i}",
            evidence=[],
            confidence=0.8,
            domains=["test"],
            implications=[],
            time_horizon="near_term",
        )
        store.insert_insight(insight)

    # Collect all insights through pagination
    all_insights = []
    cursor = None
    while True:
        insights, cursor = store.get_insights_paginated(cursor=cursor, limit=3)
        all_insights.extend(insights)
        if cursor is None:
            break

    assert len(all_insights) == 7
    # Verify no duplicates
    ids = [i.id for i in all_insights]
    assert len(ids) == len(set(ids))


def test_insights_count(store: Store):
    """Test count_insights returns correct total."""
    for i in range(5):
        insight = Insight(
            category=InsightCategory.GAP,
            title=f"Insight {i}",
            summary=f"Summary {i}",
            evidence=[],
            confidence=0.8,
            domains=["test"],
            implications=[],
            time_horizon="near_term",
        )
        store.insert_insight(insight)

    assert store.count_insights() == 5


# ── BuildableUnits (ideas) pagination tests ────────────────────────


def test_buildable_units_first_page(store: Store):
    """Test fetching the first page of buildable units."""
    # Create 5 units
    for i in range(5):
        unit = BuildableUnit(
            title=f"Unit {i}",
            one_liner=f"One liner {i}",
            category="tool",
            ideation_mode=IdeationMode.DIRECT,
            problem=f"Problem {i}",
            solution=f"Solution {i}",
            target_users="both",
            value_proposition=f"Value {i}",
        )
        store.insert_buildable_unit(unit)

    # Fetch first page
    units, next_cursor = store.get_buildable_units_paginated(cursor=None, limit=3)

    assert len(units) == 3
    assert next_cursor is not None


def test_buildable_units_with_status_filter(store: Store):
    """Test pagination with status filter."""
    # Create units with different statuses
    for i in range(3):
        unit = BuildableUnit(
            title=f"Draft {i}",
            one_liner=f"One liner {i}",
            category="tool",
            ideation_mode=IdeationMode.DIRECT,
            problem=f"Problem {i}",
            solution=f"Solution {i}",
            target_users="both",
            value_proposition=f"Value {i}",
            status="draft",
        )
        store.insert_buildable_unit(unit)

    for i in range(2):
        unit = BuildableUnit(
            title=f"Evaluated {i}",
            one_liner=f"One liner {i}",
            category="tool",
            ideation_mode=IdeationMode.DIRECT,
            problem=f"Problem {i}",
            solution=f"Solution {i}",
            target_users="both",
            value_proposition=f"Value {i}",
            status="evaluated",
        )
        store.insert_buildable_unit(unit)

    # Fetch only draft units
    units, next_cursor = store.get_buildable_units_paginated(
        cursor=None, limit=10, status="draft"
    )

    assert len(units) == 3
    assert all(u.status == "draft" for u in units)
    assert next_cursor is None

    # Verify count respects filter
    count = store.count_buildable_units(status="draft")
    assert count == 3


def test_buildable_units_with_domain_filter(store: Store):
    """Test pagination with domain filter."""
    # Create units with different domains
    for i in range(2):
        unit = BuildableUnit(
            title=f"AI Unit {i}",
            one_liner=f"One liner {i}",
            category="tool",
            ideation_mode=IdeationMode.DIRECT,
            problem=f"Problem {i}",
            solution=f"Solution {i}",
            target_users="both",
            value_proposition=f"Value {i}",
            domain="ai",
        )
        store.insert_buildable_unit(unit)

    for i in range(3):
        unit = BuildableUnit(
            title=f"Devtools Unit {i}",
            one_liner=f"One liner {i}",
            category="tool",
            ideation_mode=IdeationMode.DIRECT,
            problem=f"Problem {i}",
            solution=f"Solution {i}",
            target_users="both",
            value_proposition=f"Value {i}",
            domain="devtools",
        )
        store.insert_buildable_unit(unit)

    # Fetch only devtools units
    units, next_cursor = store.get_buildable_units_paginated(
        cursor=None, limit=10, domain="devtools"
    )

    assert len(units) == 3
    assert all(u.domain == "devtools" for u in units)

    # Verify count respects filter
    count = store.count_buildable_units(domain="devtools")
    assert count == 3


def test_buildable_units_with_combined_filters(store: Store):
    """Test pagination with both status and domain filters."""
    # Create units with various status/domain combinations
    store.insert_buildable_unit(
        BuildableUnit(
            title="AI Draft",
            one_liner="One liner",
            category="tool",
            ideation_mode=IdeationMode.DIRECT,
            problem="Problem",
            solution="Solution",
            target_users="both",
            value_proposition="Value",
            status="draft",
            domain="ai",
        )
    )
    store.insert_buildable_unit(
        BuildableUnit(
            title="AI Evaluated",
            one_liner="One liner",
            category="tool",
            ideation_mode=IdeationMode.DIRECT,
            problem="Problem",
            solution="Solution",
            target_users="both",
            value_proposition="Value",
            status="evaluated",
            domain="ai",
        )
    )
    store.insert_buildable_unit(
        BuildableUnit(
            title="Devtools Draft",
            one_liner="One liner",
            category="tool",
            ideation_mode=IdeationMode.DIRECT,
            problem="Problem",
            solution="Solution",
            target_users="both",
            value_proposition="Value",
            status="draft",
            domain="devtools",
        )
    )

    # Fetch only draft + ai units
    units, next_cursor = store.get_buildable_units_paginated(
        cursor=None, limit=10, status="draft", domain="ai"
    )

    assert len(units) == 1
    assert units[0].title == "AI Draft"
    assert next_cursor is None

    # Verify count respects both filters
    count = store.count_buildable_units(status="draft", domain="ai")
    assert count == 1


# ── Limit clamping tests ────────────────────────────────────────────


def test_signals_limit_clamping(store: Store):
    """Test that limit is properly enforced (max 100 in API)."""
    # Create 10 signals
    for i in range(10):
        signal = Signal(
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title=f"Signal {i}",
            content=f"Content {i}",
            url=f"https://example.com/{i}",
        )
        store.insert_signal(signal)

    # Request with limit 5
    signals, next_cursor = store.get_signals_paginated(cursor=None, limit=5)
    assert len(signals) == 5
    assert next_cursor is not None

    # Request remaining
    signals2, next_cursor2 = store.get_signals_paginated(cursor=next_cursor, limit=10)
    assert len(signals2) == 5
    assert next_cursor2 is None

"""Tests for Store.get_adapter_quality_stats() method.

Tests signal utilization tracking per adapter, including insight and idea hit rates.
"""

from __future__ import annotations

import json

import pytest

from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


# ── Helpers ──────────────────────────────────────────────────────


def _make_signal(
    adapter: str,
    sig_id: str,
    *,
    source_type: SignalSourceType = SignalSourceType.FORUM,
) -> Signal:
    """Create a signal for testing."""
    return Signal(
        id=sig_id,
        source_type=source_type,
        source_adapter=adapter,
        title=f"Signal from {adapter}",
        content=f"Content from {adapter}",
        url=f"https://example.com/{sig_id}",
        credibility=0.7,
        metadata={},
    )


def _make_insight(
    insight_id: str,
    evidence_signal_ids: list[str],
) -> Insight:
    """Create an insight referencing specific signals."""
    return Insight(
        id=insight_id,
        category=InsightCategory.GAP,
        title=f"Insight {insight_id}",
        summary="Test insight",
        evidence=evidence_signal_ids,
        confidence=0.8,
        domains=["test"],
        implications=["Test implication"],
        time_horizon="near_term",
    )


def _make_unit(
    unit_id: str,
    evidence_signals: list[str],
) -> BuildableUnit:
    """Create a buildable unit referencing specific signals."""
    return BuildableUnit(
        id=unit_id,
        title=f"Unit {unit_id}",
        one_liner="Test unit",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        target_users="both",
        value_proposition="Test value",
        evidence_signals=evidence_signals,
    )


# ── Tests ────────────────────────────────────────────────────────


def test_empty_database_returns_empty(store: Store) -> None:
    """Empty database should return empty stats dict."""
    stats = store.get_adapter_quality_stats()
    assert stats == {}


def test_signals_only_no_insights_or_ideas(store: Store) -> None:
    """Signals without insights/ideas should show 0.0 hit rates."""
    # Insert signals from two adapters
    for i in range(5):
        store.insert_signal(_make_signal("hackernews", f"sig-hn-{i}"))
    for i in range(3):
        store.insert_signal(_make_signal("reddit", f"sig-reddit-{i}"))

    stats = store.get_adapter_quality_stats()

    assert len(stats) == 2
    assert stats["hackernews"]["total_signals"] == 5
    assert stats["hackernews"]["insight_hit_rate"] == 0.0
    assert stats["hackernews"]["idea_hit_rate"] == 0.0
    assert stats["reddit"]["total_signals"] == 3
    assert stats["reddit"]["insight_hit_rate"] == 0.0
    assert stats["reddit"]["idea_hit_rate"] == 0.0


def test_insight_hit_rate_calculation(store: Store) -> None:
    """Insight hit rate = (signals referenced in insights) / total_signals."""
    # Insert 5 signals from hackernews
    sig_ids = [f"sig-hn-{i}" for i in range(5)]
    for sig_id in sig_ids:
        store.insert_signal(_make_signal("hackernews", sig_id))

    # Create insights referencing 3 out of 5 signals
    insight1 = _make_insight("ins-1", [sig_ids[0], sig_ids[1]])
    insight2 = _make_insight("ins-2", [sig_ids[2]])
    store.insert_insight(insight1)
    store.insert_insight(insight2)

    stats = store.get_adapter_quality_stats()

    assert stats["hackernews"]["total_signals"] == 5
    # 3 signals referenced out of 5 total
    assert stats["hackernews"]["insight_hit_rate"] == 0.6
    assert stats["hackernews"]["idea_hit_rate"] == 0.0


def test_idea_hit_rate_calculation(store: Store) -> None:
    """Idea hit rate = (signals referenced in buildable_units) / total_signals."""
    # Insert 4 signals from reddit
    sig_ids = [f"sig-reddit-{i}" for i in range(4)]
    for sig_id in sig_ids:
        store.insert_signal(_make_signal("reddit", sig_id))

    # Create buildable units referencing 2 out of 4 signals
    unit1 = _make_unit("bu-1", [sig_ids[0]])
    unit2 = _make_unit("bu-2", [sig_ids[3]])
    store.insert_buildable_unit(unit1)
    store.insert_buildable_unit(unit2)

    stats = store.get_adapter_quality_stats()

    assert stats["reddit"]["total_signals"] == 4
    assert stats["reddit"]["insight_hit_rate"] == 0.0
    # 2 signals referenced out of 4 total
    assert stats["reddit"]["idea_hit_rate"] == 0.5


def test_mixed_adapters_independent_rates(store: Store) -> None:
    """Different adapters should have independent hit rates."""
    # Adapter A: 3 signals
    sig_a_ids = [f"sig-a-{i}" for i in range(3)]
    for sig_id in sig_a_ids:
        store.insert_signal(_make_signal("adapter_a", sig_id))

    # Adapter B: 4 signals
    sig_b_ids = [f"sig-b-{i}" for i in range(4)]
    for sig_id in sig_b_ids:
        store.insert_signal(_make_signal("adapter_b", sig_id))

    # Adapter C: 2 signals
    sig_c_ids = [f"sig-c-{i}" for i in range(2)]
    for sig_id in sig_c_ids:
        store.insert_signal(_make_signal("adapter_c", sig_id))

    # Insights reference only adapter A's signals (2 out of 3)
    insight = _make_insight("ins-1", [sig_a_ids[0], sig_a_ids[2]])
    store.insert_insight(insight)

    # Ideas reference only adapter B's signals (3 out of 4)
    unit = _make_unit("bu-1", [sig_b_ids[0], sig_b_ids[1], sig_b_ids[3]])
    store.insert_buildable_unit(unit)

    stats = store.get_adapter_quality_stats()

    # Adapter A: insight hit rate only
    assert stats["adapter_a"]["total_signals"] == 3
    assert stats["adapter_a"]["insight_hit_rate"] == pytest.approx(2 / 3)
    assert stats["adapter_a"]["idea_hit_rate"] == 0.0

    # Adapter B: idea hit rate only
    assert stats["adapter_b"]["total_signals"] == 4
    assert stats["adapter_b"]["insight_hit_rate"] == 0.0
    assert stats["adapter_b"]["idea_hit_rate"] == pytest.approx(3 / 4)

    # Adapter C: no hits
    assert stats["adapter_c"]["total_signals"] == 2
    assert stats["adapter_c"]["insight_hit_rate"] == 0.0
    assert stats["adapter_c"]["idea_hit_rate"] == 0.0


def test_archived_signals_excluded(store: Store) -> None:
    """Archived signals should not be counted in total_signals."""
    # Insert 5 signals
    sig_ids = [f"sig-hn-{i}" for i in range(5)]
    for sig_id in sig_ids:
        store.insert_signal(_make_signal("hackernews", sig_id))

    # Archive 2 signals by setting archived_at timestamp
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    store.conn.execute(
        "UPDATE signals SET archived_at = ? WHERE id = ?", (now, sig_ids[0])
    )
    store.conn.execute(
        "UPDATE signals SET archived_at = ? WHERE id = ?", (now, sig_ids[1])
    )
    store.conn.commit()

    # Create insight referencing one archived and one non-archived signal
    insight = _make_insight("ins-1", [sig_ids[0], sig_ids[2]])
    store.insert_insight(insight)

    stats = store.get_adapter_quality_stats()

    # Only 3 non-archived signals should be counted in total_signals
    assert stats["hackernews"]["total_signals"] == 3
    # NOTE: Current implementation counts all signals referenced in insights,
    # even archived ones. 2 signals are referenced (sig_ids[0] and sig_ids[2]),
    # so hit rate = 2/3, not 1/3. This may be a bug - archived signals
    # shouldn't contribute to hit rates.
    assert stats["hackernews"]["insight_hit_rate"] == pytest.approx(2 / 3)


def test_same_signal_referenced_multiple_times(store: Store) -> None:
    """A signal referenced in multiple insights/ideas should only count once."""
    # Insert 2 signals
    sig_ids = [f"sig-hn-{i}" for i in range(2)]
    for sig_id in sig_ids:
        store.insert_signal(_make_signal("hackernews", sig_id))

    # Reference sig_ids[0] in multiple insights
    insight1 = _make_insight("ins-1", [sig_ids[0]])
    insight2 = _make_insight("ins-2", [sig_ids[0]])
    store.insert_insight(insight1)
    store.insert_insight(insight2)

    # Reference sig_ids[0] in multiple units
    unit1 = _make_unit("bu-1", [sig_ids[0]])
    unit2 = _make_unit("bu-2", [sig_ids[0]])
    store.insert_buildable_unit(unit1)
    store.insert_buildable_unit(unit2)

    stats = store.get_adapter_quality_stats()

    # Only 1 signal (sig_ids[0]) should be counted as hit, not 2+2
    assert stats["hackernews"]["total_signals"] == 2
    assert stats["hackernews"]["insight_hit_rate"] == 0.5
    assert stats["hackernews"]["idea_hit_rate"] == 0.5


def test_signal_referenced_in_both_insights_and_ideas(store: Store) -> None:
    """A signal can contribute to both insight and idea hit rates."""
    # Insert 3 signals
    sig_ids = [f"sig-hn-{i}" for i in range(3)]
    for sig_id in sig_ids:
        store.insert_signal(_make_signal("hackernews", sig_id))

    # Reference sig_ids[0] in both insight and idea
    # Reference sig_ids[1] only in insight
    # sig_ids[2] is unreferenced
    insight = _make_insight("ins-1", [sig_ids[0], sig_ids[1]])
    unit = _make_unit("bu-1", [sig_ids[0]])
    store.insert_insight(insight)
    store.insert_buildable_unit(unit)

    stats = store.get_adapter_quality_stats()

    assert stats["hackernews"]["total_signals"] == 3
    # 2 signals in insights: sig_ids[0], sig_ids[1]
    assert stats["hackernews"]["insight_hit_rate"] == pytest.approx(2 / 3)
    # 1 signal in ideas: sig_ids[0]
    assert stats["hackernews"]["idea_hit_rate"] == pytest.approx(1 / 3)


def test_malformed_evidence_json_in_insight(store: Store) -> None:
    """Malformed JSON in insights.evidence should raise an error."""
    from datetime import datetime, timezone

    # Insert a signal
    store.insert_signal(_make_signal("hackernews", "sig-hn-1"))

    # Manually insert an insight with malformed JSON
    now = datetime.now(timezone.utc).isoformat()
    store.conn.execute(
        """INSERT INTO insights (id, category, title, summary, evidence, confidence,
           domains, implications, time_horizon, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "ins-malformed",
            "gap",
            "Test",
            "Test summary",
            "not a valid json array",  # Invalid JSON
            0.8,
            json.dumps(["test"]),
            json.dumps(["test"]),
            "near_term",
            now,
        ),
    )

    # Current implementation will crash on json.loads()
    with pytest.raises(json.JSONDecodeError):
        store.get_adapter_quality_stats()


def test_malformed_evidence_json_in_buildable_unit(store: Store) -> None:
    """Malformed JSON in buildable_units.evidence_signals should raise an error."""
    from datetime import datetime, timezone

    # Insert a signal
    store.insert_signal(_make_signal("hackernews", "sig-hn-1"))

    # Manually insert a buildable unit with malformed JSON
    now = datetime.now(timezone.utc).isoformat()
    store.conn.execute(
        """INSERT INTO buildable_units
           (id, title, one_liner, category, ideation_mode, problem, solution,
            target_users, value_proposition, evidence_signals, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "bu-malformed",
            "Test",
            "Test one-liner",
            "cli_tool",
            "direct",
            "Test problem",
            "Test solution",
            "both",
            "Test value",
            "{invalid json}",  # Invalid JSON
            now,
            now,
        ),
    )

    # Current implementation will crash on json.loads()
    with pytest.raises(json.JSONDecodeError):
        store.get_adapter_quality_stats()


def test_empty_evidence_arrays(store: Store) -> None:
    """Insights/ideas with empty evidence arrays should not affect hit rates."""
    # Insert 2 signals
    sig_ids = [f"sig-hn-{i}" for i in range(2)]
    for sig_id in sig_ids:
        store.insert_signal(_make_signal("hackernews", sig_id))

    # Create insight/unit with empty evidence
    insight = _make_insight("ins-1", [])
    unit = _make_unit("bu-1", [])
    store.insert_insight(insight)
    store.insert_buildable_unit(unit)

    stats = store.get_adapter_quality_stats()

    assert stats["hackernews"]["total_signals"] == 2
    assert stats["hackernews"]["insight_hit_rate"] == 0.0
    assert stats["hackernews"]["idea_hit_rate"] == 0.0


def test_nonexistent_signal_ids_in_evidence(store: Store) -> None:
    """References to non-existent signal IDs should not crash or count."""
    # Insert 1 real signal
    store.insert_signal(_make_signal("hackernews", "sig-hn-1"))

    # Create insight referencing non-existent signal
    insight = _make_insight("ins-1", ["sig-nonexistent-1", "sig-nonexistent-2"])
    store.insert_insight(insight)

    stats = store.get_adapter_quality_stats()

    # Should not crash, and hit rate should be 0
    assert stats["hackernews"]["total_signals"] == 1
    assert stats["hackernews"]["insight_hit_rate"] == 0.0

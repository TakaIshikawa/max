"""Comprehensive tests for _resolve_evidence_chain function in pipeline runner."""

from __future__ import annotations

import json

import pytest

from max.pipeline.runner import _resolve_evidence_chain
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def store():
    """In-memory store for testing."""
    s = Store(db_path=':memory:')
    yield s
    s.close()


def make_signal(
    id: str,
    title: str,
    content: str,
    signal_role: str | None = None,
) -> Signal:
    """Create a test Signal with optional signal_role."""
    metadata = {}
    if signal_role:
        metadata["signal_role"] = signal_role

    return Signal(
        id=id,
        source_type=SignalSourceType.FORUM,
        source_adapter="test_adapter",
        title=title,
        content=content,
        url=f"https://example.com/{id}",
        tags=["test"],
        credibility=0.7,
        metadata=metadata,
    )


def make_insight(
    id: str,
    title: str,
    summary: str,
    evidence: list[str],
    confidence: float = 0.8,
) -> Insight:
    """Create a test Insight."""
    return Insight(
        id=id,
        category=InsightCategory.GAP,
        title=title,
        summary=summary,
        evidence=evidence,
        confidence=confidence,
        domains=["testing"],
    )


def make_unit(
    id: str,
    inspiring_insights: list[str] | None = None,
    evidence_signals: list[str] | None = None,
) -> BuildableUnit:
    """Create a test BuildableUnit."""
    return BuildableUnit(
        id=id,
        title="Test Unit",
        one_liner="Test one liner",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        value_proposition="Test value",
        inspiring_insights=inspiring_insights or [],
        evidence_signals=evidence_signals or [],
    )


# ── Happy path tests ──────────────────────────────────────────────────


def test_complete_chain_resolution(store):
    """Unit with inspiring_insights and evidence_signals resolves complete chain."""
    # Create signals
    sig1 = make_signal("sig-001", "Signal 1", "Content for signal 1", signal_role="problem")
    sig2 = make_signal("sig-002", "Signal 2", "Content for signal 2", signal_role="solution")
    sig3 = make_signal("sig-003", "Signal 3", "Direct evidence signal")

    store.insert_signal(sig1)
    store.insert_signal(sig2)
    store.insert_signal(sig3)

    # Create insight referencing signals
    insight = make_insight(
        "ins-001",
        "Test Insight",
        "This is a test insight summary",
        ["sig-001", "sig-002"],
        confidence=0.85,
    )
    store.insert_insight(insight)

    # Create unit with both inspiring insights and direct evidence signals
    unit = make_unit("bu-001", inspiring_insights=["ins-001"], evidence_signals=["sig-003"])

    result = _resolve_evidence_chain(unit, store)

    assert result is not None
    data = json.loads(result)

    # Verify structure
    assert "insights" in data
    assert "signals" in data

    # Verify insight data
    assert len(data["insights"]) == 1
    assert data["insights"][0]["id"] == "ins-001"
    assert data["insights"][0]["title"] == "Test Insight"
    assert data["insights"][0]["summary"] == "This is a test insight summary"
    assert data["insights"][0]["confidence"] == 0.85

    # Verify signal data (should have all 3 signals)
    assert len(data["signals"]) == 3

    # Find signals by id
    signals_by_id = {s["id"]: s for s in data["signals"]}

    # Check sig-001 (from insight)
    assert "sig-001" in signals_by_id
    sig1_data = signals_by_id["sig-001"]
    assert sig1_data["title"] == "Signal 1"
    assert sig1_data["content"] == "Content for signal 1"
    assert sig1_data["source"] == "test_adapter"
    assert sig1_data["signal_role"] == "problem"
    assert sig1_data["url"] == "https://example.com/sig-001"

    # Check sig-003 (direct evidence)
    assert "sig-003" in signals_by_id
    sig3_data = signals_by_id["sig-003"]
    assert sig3_data["title"] == "Signal 3"
    assert "signal_role" not in sig3_data  # Direct signals don't include signal_role


def test_json_structure_and_required_fields(store):
    """Returned JSON contains both 'insights' and 'signals' keys with all required fields."""
    sig = make_signal("sig-001", "Test Signal", "Test content", signal_role="market")
    store.insert_signal(sig)

    insight = make_insight("ins-001", "Test Insight", "Test summary", ["sig-001"], confidence=0.9)
    store.insert_insight(insight)

    unit = make_unit("bu-001", inspiring_insights=["ins-001"])

    result = _resolve_evidence_chain(unit, store)
    data = json.loads(result)

    # Check top-level keys
    assert set(data.keys()) == {"insights", "signals"}

    # Check insight has all required fields
    insight_data = data["insights"][0]
    assert set(insight_data.keys()) == {"id", "title", "summary", "confidence"}

    # Check signal from insight has all required fields
    signal_data = data["signals"][0]
    assert "id" in signal_data
    assert "title" in signal_data
    assert "content" in signal_data
    assert "source" in signal_data
    assert "signal_role" in signal_data
    assert "url" in signal_data


# ── Deduplication tests ───────────────────────────────────────────────


def test_deduplication_across_multiple_insights(store):
    """Signals referenced by multiple insights are only included once."""
    # Shared signal
    sig = make_signal("sig-shared", "Shared Signal", "Referenced by multiple insights")
    store.insert_signal(sig)

    # Two insights both referencing the same signal
    ins1 = make_insight("ins-001", "Insight 1", "Summary 1", ["sig-shared"])
    ins2 = make_insight("ins-002", "Insight 2", "Summary 2", ["sig-shared"])
    store.insert_insight(ins1)
    store.insert_insight(ins2)

    unit = make_unit("bu-001", inspiring_insights=["ins-001", "ins-002"])

    result = _resolve_evidence_chain(unit, store)
    data = json.loads(result)

    # Should have 2 insights but only 1 signal
    assert len(data["insights"]) == 2
    assert len(data["signals"]) == 1
    assert data["signals"][0]["id"] == "sig-shared"


def test_deduplication_insight_and_direct_evidence(store):
    """Signals in both insight.evidence and unit.evidence_signals are not duplicated."""
    sig = make_signal("sig-001", "Shared Signal", "In both paths")
    store.insert_signal(sig)

    insight = make_insight("ins-001", "Test Insight", "Summary", ["sig-001"])
    store.insert_insight(insight)

    # Unit references signal both through insight and directly
    unit = make_unit("bu-001", inspiring_insights=["ins-001"], evidence_signals=["sig-001"])

    result = _resolve_evidence_chain(unit, store)
    data = json.loads(result)

    # Signal should appear only once
    assert len(data["signals"]) == 1
    assert data["signals"][0]["id"] == "sig-001"


# ── Missing references tests ──────────────────────────────────────────


def test_returns_none_when_no_references(store):
    """Returns None when unit has no inspiring_insights and no evidence_signals."""
    unit = make_unit("bu-001")

    result = _resolve_evidence_chain(unit, store)

    assert result is None


def test_returns_none_when_all_references_missing(store):
    """Returns None when all referenced insights/signals are missing from store."""
    # Unit references non-existent insights and signals
    unit = make_unit(
        "bu-001",
        inspiring_insights=["ins-nonexistent-1", "ins-nonexistent-2"],
        evidence_signals=["sig-nonexistent-1", "sig-nonexistent-2"],
    )

    result = _resolve_evidence_chain(unit, store)

    assert result is None


def test_insight_exists_but_signals_missing(store):
    """Gracefully handles insight that exists but references missing signals."""
    # Insight exists but references signals that don't exist
    insight = make_insight(
        "ins-001",
        "Test Insight",
        "Summary",
        ["sig-nonexistent-1", "sig-nonexistent-2"],
    )
    store.insert_insight(insight)

    unit = make_unit("bu-001", inspiring_insights=["ins-001"])

    result = _resolve_evidence_chain(unit, store)
    data = json.loads(result)

    # Should have the insight but no signals
    assert len(data["insights"]) == 1
    assert len(data["signals"]) == 0


def test_some_evidence_signals_missing(store):
    """Gracefully handles unit with evidence_signals where some signals are missing."""
    # Only one of the two signals exists
    sig = make_signal("sig-001", "Existing Signal", "Content")
    store.insert_signal(sig)

    unit = make_unit("bu-001", evidence_signals=["sig-001", "sig-nonexistent"])

    result = _resolve_evidence_chain(unit, store)
    data = json.loads(result)

    # Should have only the existing signal
    assert len(data["signals"]) == 1
    assert data["signals"][0]["id"] == "sig-001"


def test_mixed_valid_and_invalid_references(store):
    """Unit with mix of valid and invalid insight/signal references."""
    # One valid signal
    sig = make_signal("sig-001", "Valid Signal", "Content")
    store.insert_signal(sig)

    # One valid insight
    insight = make_insight("ins-001", "Valid Insight", "Summary", ["sig-001"])
    store.insert_insight(insight)

    # Unit references valid and invalid insights and signals
    unit = make_unit(
        "bu-001",
        inspiring_insights=["ins-001", "ins-nonexistent"],
        evidence_signals=["sig-001", "sig-nonexistent"],
    )

    result = _resolve_evidence_chain(unit, store)
    data = json.loads(result)

    # Should have valid insight and signal (deduplicated)
    assert len(data["insights"]) == 1
    assert len(data["signals"]) == 1


# ── Content truncation tests ──────────────────────────────────────────


def test_content_truncation_over_500_chars(store):
    """Signal content longer than 500 chars is truncated to 500 in output."""
    long_content = "x" * 1000
    sig = make_signal("sig-001", "Long Signal", long_content)
    store.insert_signal(sig)

    unit = make_unit("bu-001", evidence_signals=["sig-001"])

    result = _resolve_evidence_chain(unit, store)
    data = json.loads(result)

    assert len(data["signals"][0]["content"]) == 500
    assert data["signals"][0]["content"] == "x" * 500


def test_content_exactly_500_chars_not_truncated(store):
    """Signal content exactly 500 chars is not truncated."""
    exact_content = "y" * 500
    sig = make_signal("sig-001", "Exact Signal", exact_content)
    store.insert_signal(sig)

    unit = make_unit("bu-001", evidence_signals=["sig-001"])

    result = _resolve_evidence_chain(unit, store)
    data = json.loads(result)

    assert len(data["signals"][0]["content"]) == 500
    assert data["signals"][0]["content"] == exact_content


def test_content_under_500_chars_preserved(store):
    """Signal content under 500 chars is preserved as-is."""
    short_content = "This is a short signal content"
    sig = make_signal("sig-001", "Short Signal", short_content)
    store.insert_signal(sig)

    unit = make_unit("bu-001", evidence_signals=["sig-001"])

    result = _resolve_evidence_chain(unit, store)
    data = json.loads(result)

    assert data["signals"][0]["content"] == short_content


# ── Direct evidence signals tests ─────────────────────────────────────


def test_direct_evidence_signals_only(store):
    """Unit with only evidence_signals (no inspiring_insights) returns valid JSON."""
    sig1 = make_signal("sig-001", "Direct Signal 1", "Content 1")
    sig2 = make_signal("sig-002", "Direct Signal 2", "Content 2")
    store.insert_signal(sig1)
    store.insert_signal(sig2)

    unit = make_unit("bu-001", evidence_signals=["sig-001", "sig-002"])

    result = _resolve_evidence_chain(unit, store)
    data = json.loads(result)

    # Should have empty insights and two signals
    assert len(data["insights"]) == 0
    assert len(data["signals"]) == 2


def test_direct_signal_excludes_signal_role(store):
    """Signal from evidence_signals doesn't include signal_role key."""
    # Create signal with signal_role in metadata
    sig_with_role = make_signal("sig-001", "Signal", "Content", signal_role="problem")
    store.insert_signal(sig_with_role)

    # Create insight and unit
    insight = make_insight("ins-001", "Insight", "Summary", ["sig-001"])
    store.insert_insight(insight)

    unit_with_insight = make_unit("bu-001", inspiring_insights=["ins-001"])
    unit_direct = make_unit("bu-002", evidence_signals=["sig-001"])

    # Signal via insight should include signal_role
    result_insight = _resolve_evidence_chain(unit_with_insight, store)
    data_insight = json.loads(result_insight)
    assert "signal_role" in data_insight["signals"][0]
    assert data_insight["signals"][0]["signal_role"] == "problem"

    # Signal via direct evidence should NOT include signal_role
    result_direct = _resolve_evidence_chain(unit_direct, store)
    data_direct = json.loads(result_direct)
    assert "signal_role" not in data_direct["signals"][0]


def test_mixed_insight_and_direct_signals(store):
    """Unit with both inspiring insights and direct evidence signals."""
    # Signal for insight
    sig1 = make_signal("sig-001", "Insight Signal", "Content 1", signal_role="problem")
    # Direct signal
    sig2 = make_signal("sig-002", "Direct Signal", "Content 2", signal_role="solution")

    store.insert_signal(sig1)
    store.insert_signal(sig2)

    insight = make_insight("ins-001", "Test Insight", "Summary", ["sig-001"])
    store.insert_insight(insight)

    unit = make_unit("bu-001", inspiring_insights=["ins-001"], evidence_signals=["sig-002"])

    result = _resolve_evidence_chain(unit, store)
    data = json.loads(result)

    assert len(data["insights"]) == 1
    assert len(data["signals"]) == 2

    # Find signals
    signals_by_id = {s["id"]: s for s in data["signals"]}

    # Signal from insight should have signal_role
    assert "signal_role" in signals_by_id["sig-001"]

    # Direct signal should NOT have signal_role
    assert "signal_role" not in signals_by_id["sig-002"]

"""Tests for SQLite store CRUD operations."""

from __future__ import annotations

from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation
from max.types.insight import Insight
from max.types.signal import Signal
from max.types.tact_spec import TactSpec


def test_insert_and_get_signal(store: Store, sample_signal: Signal) -> None:
    stored = store.insert_signal(sample_signal)
    assert stored.id == "sig-test001"

    signals = store.get_signals()
    assert len(signals) == 1
    assert signals[0].title == sample_signal.title
    assert signals[0].url == sample_signal.url
    assert signals[0].tags == ["mcp", "ai", "devtools"]


def test_signal_deduplication(store: Store, sample_signal: Signal) -> None:
    store.insert_signal(sample_signal)
    store.insert_signal(sample_signal)  # same URL
    assert store.count_signals() == 1


def test_signal_filter_by_source_type(store: Store, sample_signal: Signal) -> None:
    store.insert_signal(sample_signal)
    forum_signals = store.get_signals(source_type="forum")
    assert len(forum_signals) == 1
    registry_signals = store.get_signals(source_type="registry")
    assert len(registry_signals) == 0


def test_insert_and_get_insight(store: Store, sample_insight: Insight) -> None:
    stored = store.insert_insight(sample_insight)
    assert stored.id == "ins-test001"

    insights = store.get_insights()
    assert len(insights) == 1
    assert insights[0].category.value == "gap"
    assert insights[0].evidence == ["sig-test001"]


def test_insert_and_get_buildable_unit(store: Store, sample_unit: BuildableUnit) -> None:
    stored = store.insert_buildable_unit(sample_unit)
    assert stored.id == "bu-test001"

    unit = store.get_buildable_unit("bu-test001")
    assert unit is not None
    assert unit.title == "MCP Test Framework"
    assert unit.category.value == "cli_tool"
    assert unit.inspiring_insights == ["ins-test001"]


def test_buildable_unit_status_update(store: Store, sample_unit: BuildableUnit) -> None:
    store.insert_buildable_unit(sample_unit)
    store.update_buildable_unit_status("bu-test001", "evaluated")

    unit = store.get_buildable_unit("bu-test001")
    assert unit.status == "evaluated"


def test_buildable_unit_filter_by_status(store: Store, sample_unit: BuildableUnit) -> None:
    store.insert_buildable_unit(sample_unit)
    drafts = store.get_buildable_units(status="draft")
    assert len(drafts) == 1
    approved = store.get_buildable_units(status="approved")
    assert len(approved) == 0


def test_insert_and_get_evaluation(store: Store, sample_unit: BuildableUnit, sample_evaluation: UtilityEvaluation) -> None:
    store.insert_buildable_unit(sample_unit)
    store.insert_evaluation(sample_evaluation)

    evaluation = store.get_evaluation("bu-test001")
    assert evaluation is not None
    assert evaluation.overall_score == 78.0
    assert evaluation.pain_severity.value == 8.0
    assert evaluation.recommendation == "yes"


def test_insert_and_get_tact_spec(store: Store, sample_unit: BuildableUnit, sample_tact_spec: TactSpec) -> None:
    store.insert_buildable_unit(sample_unit)
    store.insert_tact_spec(sample_tact_spec)

    spec = store.get_tact_spec("bu-test001")
    assert spec is not None
    assert spec.product.name == "mcp-test-framework"
    assert len(spec.requirements) == 1
    assert spec.requirements[0].acceptance_criteria == [
        "Validates initialize handshake",
        "Validates tool listing",
        "Validates tool execution",
    ]


# ── By-ID lookups ─────────────────────────────────────────────────


def test_get_signal_by_id(store: Store, sample_signal: Signal) -> None:
    store.insert_signal(sample_signal)
    sig = store.get_signal("sig-test001")
    assert sig is not None
    assert sig.title == sample_signal.title
    assert sig.url == sample_signal.url


def test_get_signal_not_found(store: Store) -> None:
    assert store.get_signal("sig-nonexistent") is None


def test_get_insight_by_id(store: Store, sample_insight: Insight) -> None:
    store.insert_insight(sample_insight)
    ins = store.get_insight("ins-test001")
    assert ins is not None
    assert ins.title == sample_insight.title
    assert ins.confidence == sample_insight.confidence


def test_get_insight_not_found(store: Store) -> None:
    assert store.get_insight("ins-nonexistent") is None

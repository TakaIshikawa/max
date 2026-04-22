"""Tests for attribution tracking, pipeline run persistence, and approval stats."""

from __future__ import annotations

from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


def _make_score(value: float = 7.0) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.7, reasoning="test")


def _make_signal(adapter: str, sig_id: str) -> Signal:
    return Signal(
        id=sig_id,
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=f"Signal from {adapter}",
        content=f"Content from {adapter}",
        url=f"https://example.com/{sig_id}",
        credibility=0.7,
        metadata={"signal_role": "problem"},
    )


def _seed_idea_with_signals(
    store: Store,
    unit_id: str,
    adapter: str,
    signal_count: int,
    *,
    category: str = "cli_tool",
    target_users: str = "both",
) -> list[str]:
    """Seed signals + buildable unit referencing them."""
    sig_ids = []
    for i in range(signal_count):
        sid = f"sig-{adapter}-{unit_id}-{i}"
        store.insert_signal(_make_signal(adapter, sid))
        sig_ids.append(sid)

    unit = BuildableUnit(
        id=unit_id,
        title=f"Idea {unit_id}",
        one_liner="Test idea",
        category=BuildableCategory(category),
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        value_proposition="Test value",
        evidence_signals=sig_ids,
        target_users=target_users,
    )
    store.insert_buildable_unit(unit)

    # Insert evaluation so feedback can capture dimension values
    evaluation = UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_make_score(8.0),
        addressable_scale=_make_score(7.0),
        build_effort=_make_score(6.0),
        composability=_make_score(7.5),
        competitive_density=_make_score(8.0),
        timing_fit=_make_score(7.0),
        compounding_value=_make_score(6.5),
        overall_score=72.0,
        strengths=["test"],
        weaknesses=["test"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
    store.insert_evaluation(evaluation)

    return sig_ids


# ── Pipeline Run Persistence ──────────────────────────────────────


def test_pipeline_run_insert_and_query(store: Store) -> None:
    """Insert a pipeline run and read it back."""
    store.insert_pipeline_run("run-001", {"signal_limit": 30, "profile": "default"})
    runs = store.get_pipeline_runs()
    assert len(runs) == 1
    assert runs[0]["id"] == "run-001"
    assert runs[0]["config"]["signal_limit"] == 30
    assert runs[0]["completed_at"] is None


def test_pipeline_run_update(store: Store) -> None:
    """Update a pipeline run with completion metrics."""
    store.insert_pipeline_run("run-002", {})
    store.update_pipeline_run(
        "run-002",
        signals_fetched=25,
        signals_new=10,
        insights_generated=5,
        ideas_generated=3,
        ideas_evaluated=3,
        clusters_found=4,
        gaps_detected=2,
        avg_idea_score=65.5,
        fetch_allocation={"hn": 10, "reddit": 15},
        token_usage={"input": 1000, "output": 500},
    )
    runs = store.get_pipeline_runs()
    run = runs[0]
    assert run["completed_at"] is not None
    assert run["signals_fetched"] == 25
    assert run["signals_new"] == 10
    assert run["insights_generated"] == 5
    assert run["ideas_generated"] == 3
    assert run["clusters_found"] == 4
    assert run["gaps_detected"] == 2
    assert run["avg_idea_score"] == 65.5
    assert run["fetch_allocation"] == {"hn": 10, "reddit": 15}


def test_pipeline_runs_ordered_by_recency(store: Store) -> None:
    """Most recent run should come first."""
    store.insert_pipeline_run("run-old", {})
    store.update_pipeline_run("run-old", signals_fetched=1)
    store.insert_pipeline_run("run-new", {})
    runs = store.get_pipeline_runs()
    assert runs[0]["id"] == "run-new"


# ── Feedback with Attribution ─────────────────────────────────────


def test_feedback_with_attribution_empty(store: Store) -> None:
    """No feedback records → empty list."""
    assert store.get_feedback_with_attribution() == []


def test_feedback_with_attribution_traces_signals(store: Store) -> None:
    """Feedback should trace back to source adapters via evidence_signals."""
    _seed_idea_with_signals(store, "bu-att-1", "hackernews", 3)
    store.insert_feedback("bu-att-1", "approved", "good idea")

    attributed = store.get_feedback_with_attribution()
    assert len(attributed) == 1
    record = attributed[0]
    assert record["unit_id"] == "bu-att-1"
    assert record["outcome"] == "approved"
    assert "hackernews" in record["source_adapters"]
    assert len(record["evidence_signal_ids"]) == 3
    assert record["category"] == "cli_tool"
    assert record["eval_score"] == 72.0


def test_feedback_attribution_multiple_adapters(store: Store) -> None:
    """Idea with signals from multiple adapters traces to all of them."""
    sig1 = _make_signal("hackernews", "sig-hn-multi-1")
    sig2 = _make_signal("reddit", "sig-reddit-multi-1")
    store.insert_signal(sig1)
    store.insert_signal(sig2)

    unit = BuildableUnit(
        id="bu-multi",
        title="Multi-source idea",
        one_liner="Test",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test",
        solution="Test",
        value_proposition="Test",
        evidence_signals=["sig-hn-multi-1", "sig-reddit-multi-1"],
    )
    store.insert_buildable_unit(unit)
    store.insert_feedback("bu-multi", "rejected", "not useful")

    attributed = store.get_feedback_with_attribution()
    assert len(attributed) == 1
    adapters = set(attributed[0]["source_adapters"])
    assert adapters == {"hackernews", "reddit"}


# ── Adapter Approval Stats ────────────────────────────────────────


def test_adapter_approval_stats_empty(store: Store) -> None:
    """No feedback → empty stats."""
    assert store.get_adapter_approval_stats() == {}


def test_adapter_approval_stats_approved(store: Store) -> None:
    """Approved idea → adapter gets approval credit."""
    _seed_idea_with_signals(store, "bu-appr-1", "github_issues", 2)
    store.insert_feedback("bu-appr-1", "approved")

    stats = store.get_adapter_approval_stats()
    assert "github_issues" in stats
    assert stats["github_issues"]["approved"] == 1
    assert stats["github_issues"]["rejected"] == 0
    assert stats["github_issues"]["approval_rate"] == 1.0


def test_adapter_approval_stats_mixed(store: Store) -> None:
    """Mixed feedback → correct approval rate per adapter."""
    _seed_idea_with_signals(store, "bu-mix-1", "hackernews", 2)
    _seed_idea_with_signals(store, "bu-mix-2", "hackernews", 2)
    _seed_idea_with_signals(store, "bu-mix-3", "reddit", 2)

    store.insert_feedback("bu-mix-1", "approved")
    store.insert_feedback("bu-mix-2", "rejected")
    store.insert_feedback("bu-mix-3", "approved")

    stats = store.get_adapter_approval_stats()
    assert stats["hackernews"]["approved"] == 1
    assert stats["hackernews"]["rejected"] == 1
    assert stats["hackernews"]["approval_rate"] == 0.5
    assert stats["reddit"]["approval_rate"] == 1.0


def test_adapter_approval_stats_published_counts_as_approved(store: Store) -> None:
    """Published outcome should count as approved."""
    _seed_idea_with_signals(store, "bu-pub-1", "npm_registry", 2)
    store.insert_feedback("bu-pub-1", "published")

    stats = store.get_adapter_approval_stats()
    assert stats["npm_registry"]["approved"] == 1
    assert stats["npm_registry"]["approval_rate"] == 1.0


# ── Schema Migration ─────────────────────────────────────────────


def test_schema_v4_pipeline_runs_table_exists(store: Store) -> None:
    """pipeline_runs table should exist after migration."""
    cursor = store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_runs'"
    )
    assert cursor.fetchone() is not None


def test_schema_v4_feedback_pipeline_run_id_column(store: Store) -> None:
    """feedback table should have pipeline_run_id column."""
    columns = {
        row[1] for row in store.conn.execute("PRAGMA table_info(feedback)").fetchall()
    }
    assert "pipeline_run_id" in columns

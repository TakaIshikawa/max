"""Tests for profile budget efficiency reports."""

from __future__ import annotations

from max.analysis.profile_budget_efficiency_report import build_profile_budget_efficiency_report
from max.store.db import Store


def test_profile_budget_efficiency_ranks_high_cost_low_yield_first(store: Store) -> None:
    _insert_run(store, "run-expensive", "growth", "finops", "2026-05-03T00:00:00", 3.0, 50, 3, 1)
    _insert_run(store, "run-efficient", "ops", "support", "2026-05-02T00:00:00", 0.2, 80, 30, 20)
    _insert_run(store, "run-zero", "zero", "empty", "2026-05-01T00:00:00", 0.0, 0, 0, 0)

    report = build_profile_budget_efficiency_report(store, limit=10)
    repeated = build_profile_budget_efficiency_report(store, limit=10)

    assert report == repeated
    assert report["summary"]["run_count"] == 3
    assert report["summary"]["total_estimated_cost_usd"] == 3.2
    assert [(row["cohort_type"], row["cohort"]) for row in report["rows"][:2]] == [
        ("domain", "finops"),
        ("profile", "growth"),
    ]
    first = report["rows"][0]
    assert first["estimated_cost_usd"] == 3.0
    assert first["signals_fetched"] == 50
    assert first["ideas_generated"] == 1
    assert first["cost_per_signal"] == 0.06
    assert first["cost_per_idea"] == 3.0
    assert first["efficiency_band"] == "high_cost_low_yield"
    assert report["rows"][-1]["efficiency_band"] == "zero_cost"
    assert "domain:finops" in report["efficiency_bands"]["high_cost_low_yield"]
    assert any("high-cost low-yield" in action for action in report["next_actions"])


def test_profile_budget_efficiency_handles_zero_output_and_zero_cost(store: Store) -> None:
    _insert_run(store, "run-no-output", "research", "market", "2026-05-04T00:00:00", 1.25, 0, 0, 0)
    _insert_run(store, "run-free-output", "free", "community", "2026-05-03T00:00:00", 0.0, 5, 1, 1)

    report = build_profile_budget_efficiency_report(store, limit=5)
    by_key = {row["cohort_key"]: row for row in report["rows"]}

    assert by_key["profile:research"]["efficiency_band"] == "zero_output"
    assert by_key["profile:research"]["cost_per_signal"] is None
    assert by_key["profile:research"]["cost_per_idea"] is None
    assert by_key["profile:free"]["efficiency_band"] == "zero_cost"
    assert by_key["profile:free"]["output_yield"] is None


def test_profile_budget_efficiency_rejects_invalid_limit(store: Store) -> None:
    try:
        build_profile_budget_efficiency_report(store, limit=0)
    except ValueError as exc:
        assert str(exc) == "limit must be at least 1"
    else:
        raise AssertionError("expected ValueError")


def _insert_run(
    store: Store,
    run_id: str,
    profile: str,
    domain: str,
    started_at: str,
    cost: float,
    signals: int,
    insights: int,
    ideas: int,
) -> None:
    store.insert_pipeline_run(run_id, {"profile": profile, "domain": domain, "model": "gpt-4o-mini"})
    store.update_pipeline_run(
        run_id,
        status="completed",
        signals_fetched=signals,
        signals_new=signals,
        insights_generated=insights,
        ideas_generated=ideas,
        ideas_evaluated=ideas,
        token_usage={"estimated_cost_usd": cost},
    )
    store.insert_pipeline_run_domain(
        run_id,
        domain,
        {
            "signals_fetched": signals,
            "insights_generated": insights,
            "ideas_generated": ideas,
            "ideas_evaluated": ideas,
        },
    )
    store.conn.execute(
        "UPDATE pipeline_runs SET started_at = ?, completed_at = ? WHERE id = ?",
        (started_at, started_at, run_id),
    )
    store._commit()

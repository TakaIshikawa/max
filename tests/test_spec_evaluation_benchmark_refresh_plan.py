from __future__ import annotations

from max.spec.evaluation_benchmark_refresh_plan import (
    generate_evaluation_benchmark_refresh_plan,
)


def test_evaluation_benchmark_refresh_plan_flags_stale_benchmarks() -> None:
    plan = generate_evaluation_benchmark_refresh_plan(
        {
            "stale_after_days": 90,
            "benchmarks": [
                {"benchmark": "fresh QA", "last_refreshed_at": "2026-04-01", "as_of": "2026-05-01"},
                {"benchmark": "old safety", "last_refreshed_at": "2025-01-01", "as_of": "2026-05-01"},
                {"benchmark": "aged bias", "age_days": 120},
            ],
            "refresh_candidates": ["new private safety set"],
            "validation_sampling": ["10% stratified adjudication"],
            "approvers": ["eval owner approval"],
        }
    )

    assert set(plan) >= {
        "benchmark_inventory",
        "stale_benchmarks",
        "refresh_candidates",
        "validation_sampling",
        "approval_gates",
        "rollout_steps",
        "rollback_criteria",
        "evidence_references",
    }
    assert plan["summary"]["stale_after_days"] == 90
    assert [row["name"] for row in plan["stale_benchmarks"]] == ["old safety", "aged bias"]
    inventory = {row["name"]: row for row in plan["benchmark_inventory"]}
    assert inventory["fresh QA"]["is_stale"] is False
    assert inventory["old safety"]["age_days"] == 485


def test_evaluation_benchmark_refresh_plan_defaults_sections() -> None:
    plan = generate_evaluation_benchmark_refresh_plan({})

    assert plan["schema_version"] == "max.spec.evaluation_benchmark_refresh_plan.v1"
    assert plan["summary"]["stale_after_days"] == 180
    assert plan["summary"]["stale_benchmark_count"] == 1
    assert plan["refresh_candidates"][0]["name"] == "evaluation benchmark"
    assert plan["validation_sampling"]
    assert plan["approval_gates"]

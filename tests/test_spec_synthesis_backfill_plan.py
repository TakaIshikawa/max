from __future__ import annotations

from max.spec.synthesis_backfill_plan import generate_synthesis_backfill_plan


def test_synthesis_backfill_plan_has_deterministic_budget_and_batch_sections() -> None:
    plan = generate_synthesis_backfill_plan({"reason": "prompt_change", "signal_ranges": ["r2", "r1"], "batch_size": 250, "budget": {"max_tokens": 1000}})

    assert plan["backfill_reason"] == "prompt_change"
    assert plan["reason_supported"] is True
    assert plan["candidate_signal_ranges"] == [{"range_id": "r2"}, {"range_id": "r1"}]
    assert plan["batching_strategy"]["batch_size"] == 250
    assert plan["budget_guardrails"]["max_tokens"] == 1000
    assert len(plan["deduplication_checks"]) == 2

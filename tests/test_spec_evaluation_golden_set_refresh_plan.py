from __future__ import annotations

from max.spec import generate_evaluation_golden_set_refresh_plan


def test_evaluation_golden_set_refresh_plan_full_and_deterministic() -> None:
    payload = {"metadata": {"evaluation_golden_set_refresh": {"dataset_inventory": [{"name": "gold-v1", "sample_count": 20}], "refresh_triggers": ["drift"]}}}
    first = generate_evaluation_golden_set_refresh_plan(payload)
    second = generate_evaluation_golden_set_refresh_plan(payload)
    assert first == second
    assert first["dataset_inventory"][0]["name"] == "gold-v1"
    assert first["refresh_triggers"][0]["name"] == "drift"
    assert first["regression_checks"]


def test_evaluation_golden_set_refresh_plan_sparse_defaults() -> None:
    plan = generate_evaluation_golden_set_refresh_plan({})
    assert plan["dataset_inventory"]
    assert plan["validation_sampling"] if "validation_sampling" in plan else plan["sampling_strategy"]
    assert plan["rollback_criteria"]

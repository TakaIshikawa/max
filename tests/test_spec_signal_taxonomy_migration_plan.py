from __future__ import annotations

from max.spec.signal_taxonomy_migration_plan import generate_signal_taxonomy_migration_plan


def test_plan_identifies_unmapped_categories() -> None:
    plan = generate_signal_taxonomy_migration_plan(
        {"categories": ["problem", "evidence"]},
        {"categories": ["need"], "mappings": {"problem": "need"}},
        [{"category": "problem"}, {"category": "evidence"}],
    )

    assert plan["unmapped_categories"] == [{"category": "evidence", "reason": "No target taxonomy mapping defined."}]
    assert plan["summary"]["unmapped_category_count"] == 1


def test_plan_aggregates_affected_signal_counts() -> None:
    plan = generate_signal_taxonomy_migration_plan(
        {"categories": ["problem", "evidence"]},
        {"categories": ["need", "proof"], "mappings": {"problem": "need", "evidence": "proof"}},
        [{"category": "problem"}, {"role": "problem"}, {"signal_category": "evidence"}],
    )

    assert plan["summary"]["affected_signal_count"] == 3
    assert plan["affected_signal_counts"] == [{"category": "evidence", "signal_count": 1}, {"category": "problem", "signal_count": 2}]


def test_plan_reflects_dry_run_mode_in_generated_tasks() -> None:
    plan = generate_signal_taxonomy_migration_plan({"categories": ["problem"]}, {"categories": ["problem"]}, [], dry_run=True)

    assert plan["mode"] == "dry_run"
    assert plan["summary"]["dry_run"] is True
    assert all(step["dry_run"] is True and step["step"].startswith("Dry-run:") for step in plan["backfill_steps"])


def test_plan_outputs_deterministic_mappings_validation_and_rollback() -> None:
    payload = (
        {"categories": ["zeta", "alpha"]},
        {"categories": ["a", "z"], "mappings": [{"from": "zeta", "to": "z"}, {"from": "alpha", "to": "a"}]},
        [{"category": "zeta"}, {"category": "alpha"}],
    )

    first = generate_signal_taxonomy_migration_plan(*payload, dry_run=False)
    second = generate_signal_taxonomy_migration_plan(*payload, dry_run=False)
    assert first == second
    assert first["mappings"] == [{"from": "alpha", "to": "a", "mapped": True}, {"from": "zeta", "to": "z", "mapped": True}]
    assert first["validation_queries"]
    assert first["rollback"]

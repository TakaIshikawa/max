from __future__ import annotations

from max.spec import generate_feedback_taxonomy_migration_plan


def test_feedback_taxonomy_migration_complete_mapping_has_no_blockers() -> None:
    plan = generate_feedback_taxonomy_migration_plan({"metadata": {"feedback_taxonomy_migration": {"current_taxonomy": ["bug"], "proposed_taxonomy": ["defect"], "mapping_rules": [{"from": "bug", "to": "defect"}]}}})
    assert plan["blockers"] == []
    assert plan["mapping_rules"][0]["from"] == "bug"


def test_feedback_taxonomy_migration_missing_mapping_and_sparse_payload() -> None:
    plan = generate_feedback_taxonomy_migration_plan({"metadata": {"feedback_taxonomy_migration": {"current_taxonomy": ["bug", "idea"], "mapping_rules": [{"from": "bug", "to": "defect"}]}}})
    assert plan["blockers"] == [{"label": "idea", "reason": "Legacy label has no deterministic mapping rule."}]
    sparse = generate_feedback_taxonomy_migration_plan({})
    assert sparse["blockers"]
    assert sparse["validation_checks"]

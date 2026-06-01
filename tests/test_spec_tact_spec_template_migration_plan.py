from __future__ import annotations

from max.spec.tact_spec_template_migration_plan import generate_tact_spec_template_migration_plan


def test_outdated_templates_are_grouped_into_batches() -> None:
    plan = generate_tact_spec_template_migration_plan({"metadata": {"tact_spec_template_migration": {"target_version": "v3", "templates": [{"id": "a", "version": "v1"}, {"id": "b", "version": "v2"}]}}})
    assert plan["summary"]["outdated_count"] == 2
    assert plan["migration_batches"][0]["template_ids"] == ["a", "b"]


def test_incompatible_or_missing_fields_get_repairs() -> None:
    plan = generate_tact_spec_template_migration_plan({"templates": [{"id": "a", "version": "v1", "incompatible_fields": ["old"], "missing_fields": ["new"]}]})
    assert plan["compatibility_repairs"][0]["fields"] == ["old", "new"]


def test_validation_gates_include_regenerated_schema_checks() -> None:
    plan = generate_tact_spec_template_migration_plan({})
    assert "regenerated spec schema checks" in plan["verification_gates"][0]["check"]

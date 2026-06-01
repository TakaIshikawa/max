from __future__ import annotations

from max.spec import generate_publication_destination_migration_plan


def test_publication_destination_migration_plan_sorts_waves_and_checks_payload_mapping() -> None:
    plan = generate_publication_destination_migration_plan({"destinations": [{"destination": "zeta", "planned_at": "2026-06-02"}, {"destination": "alpha", "planned_at": "2026-06-01"}]})

    assert plan["schema_version"] == "max.spec.publication_destination_migration_plan.v1"
    assert plan["kind"] == "max.spec.publication_destination_migration_plan"
    assert [row["target_destination"] for row in plan["migration_waves"]] == ["alpha", "zeta"]
    assert {row["check"] for row in plan["payload_mapping_checks"]} == {"authentication", "field_mapping", "quota", "webhook_delivery"}

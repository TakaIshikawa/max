from __future__ import annotations

from max.spec.source_adapter_deprecation_plan import generate_source_adapter_deprecation_plan


def test_source_adapter_deprecation_plan_includes_inventory_profiles_validation_and_unknowns() -> None:
    plan = generate_source_adapter_deprecation_plan({"adapter": {"id": "legacy", "owner": ""}, "affected_profiles": ["z", "a"], "replacement_sources": ["new"]})

    assert plan["adapter_inventory"]["adapter_id"] == "legacy"
    assert plan["affected_profiles"] == ["a", "z"]
    assert plan["fallback_source_mapping"][0] == {"profile": "a", "fallback_source": "new"}
    assert [gate["id"] for gate in plan["validation_gates"]] == ["VAL1", "VAL2", "VAL3"]
    assert "owner" in plan["unknowns"]

from __future__ import annotations

from max.spec import generate_blue_green_cutover_plan


def test_blue_green_cutover_plan_full_payload_and_ordered_phases() -> None:
    plan = generate_blue_green_cutover_plan({"metadata": {"blue_green_cutover": {"service": "checkout", "traffic_phases": ["50% green", "10% green"], "validation_probes": ["checkout probe"], "rollback_triggers": ["error spike"], "owner_roles": ["release owner"]}}})

    assert plan["scope"]["service"] == "checkout"
    assert [row["name"] for row in plan["cutover_phases"]] == ["10% green", "50% green"]
    assert plan["validation_probes"][0]["name"] == "checkout probe"
    assert plan["rollback_criteria"][0]["name"] == "error spike"
    assert plan["signoff"][0]["name"] == "release owner"


def test_blue_green_cutover_plan_sparse_defaults() -> None:
    plan = generate_blue_green_cutover_plan({})

    assert plan["plan_title"] == "primary workflow blue/green cutover"
    assert plan["cutover_phases"]
    assert plan["communications"]

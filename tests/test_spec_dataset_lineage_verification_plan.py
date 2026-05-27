from __future__ import annotations

from max.spec.dataset_lineage_verification_plan import generate_dataset_lineage_verification_plan


def test_dataset_lineage_verification_plan_preserves_metadata_and_checks() -> None:
    plan = generate_dataset_lineage_verification_plan({"metadata": {"dataset_lineage_verification": {"datasets": [{"dataset": "events", "owner": "data", "upstream_source": "warehouse", "license_status": "approved"}], "verification_checks": ["row-count parity"]}}})

    assert plan["datasets"][0]["dataset"] == "events"
    assert plan["datasets"][0]["upstream_source"] == "warehouse"
    assert plan["verification_checks"][0]["name"] == "row-count parity"


def test_dataset_lineage_verification_plan_missing_fields_create_blockers() -> None:
    plan = generate_dataset_lineage_verification_plan({"metadata": {"dataset_lineage_verification": {"datasets": [{"dataset": "events"}]}}})

    assert [row["name"] for row in plan["blockers"]] == ["missing owner for events", "missing upstream source for events", "missing license or consent for events"]


def test_dataset_lineage_verification_plan_is_deterministic() -> None:
    payload = {"metadata": {"dataset_lineage_verification": {"datasets": [{"dataset": "events"}]}}}

    assert generate_dataset_lineage_verification_plan(payload) == generate_dataset_lineage_verification_plan(payload)

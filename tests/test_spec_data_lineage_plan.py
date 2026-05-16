from __future__ import annotations

from max.spec.data_lineage_plan import generate_data_lineage_plan


def test_data_lineage_plan_covers_required_sections() -> None:
    plan = generate_data_lineage_plan(
        {
            "project": {"title": "Customer 360"},
            "data": {
                "critical_datasets": ["profiles", "events"],
                "source_systems": ["crm", "warehouse"],
                "transformations": ["identity resolution"],
                "storage_destinations": ["analytics mart"],
                "owners": ["data platform"],
                "retention_references": ["retention://customer"],
                "downstream_consumers": ["cs dashboard"],
            },
            "evidence": {"insight_ids": ["lineage-1"]},
        }
    )

    assert plan["kind"] == "max.data_lineage_plan"
    assert plan["summary"]["critical_dataset_count"] == 2
    assert plan["summary"]["gap_count"] == 0
    assert plan["source_systems"] == ["crm", "warehouse"]
    assert plan["transformations"] == ["identity resolution"]
    assert plan["ownership"] == ["data platform"]
    assert plan["evidence"] == ["insight:lineage-1"]


def test_data_lineage_plan_highlights_missing_transformation_or_owner() -> None:
    plan = generate_data_lineage_plan({"data": {"critical_datasets": ["orders"]}})

    assert plan["gaps"] == [
        {"dataset": "orders", "gap": "missing transformation"},
        {"dataset": "orders", "gap": "missing owner"},
    ]
    assert plan["transformations"] == ["Unknown"]
    assert plan["ownership"] == ["Unknown"]


def test_data_lineage_plan_is_deterministic() -> None:
    payload = {"data": {"source_systems": ["z", "a", "z"], "critical_datasets": ["c"]}}

    assert generate_data_lineage_plan(payload) == generate_data_lineage_plan(payload)
    assert generate_data_lineage_plan(payload)["source_systems"] == ["a", "z"]

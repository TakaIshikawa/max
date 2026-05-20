from __future__ import annotations

from max.spec.data_residency_transfer_assessment_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_data_residency_transfer_assessment_plan,
)


def test_data_residency_transfer_blocks_restricted_transfer_without_approval() -> None:
    plan = generate_data_residency_transfer_assessment_plan(
        {
            "evidence": {"source_idea_ids": ["src-1"]},
            "metadata": {
                "data_residency_transfer_assessment": {
                    "transfer_paths": [{"name": "EU to restricted region", "from": "EU", "to": "restricted"}],
                    "approval_requirements": [{"name": "privacy approval", "status": "missing"}],
                }
            },
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["transfer_decision"] == "blocked"
    assert plan["risk_items"]
    assert plan["transfer_paths"][0]["evidence_reference_ids"] == ["EV1"]


def test_data_residency_transfer_uses_top_level_fallbacks() -> None:
    plan = generate_data_residency_transfer_assessment_plan({"transfer_paths": ["US to EU"], "approval_requirements": [{"name": "legal", "status": "approved"}]})

    assert plan["transfer_paths"][0]["name"] == "US to EU"
    assert plan["transfer_decision"] in {"approved", "conditional"}

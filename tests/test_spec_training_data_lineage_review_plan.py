from __future__ import annotations

from max.spec.training_data_lineage_review_plan import generate_training_data_lineage_review_plan


def test_training_data_lineage_review_plan_lists_complete_lineage() -> None:
    plan = generate_training_data_lineage_review_plan(
        {"datasets": [{"dataset": "support transcripts", "source": "crm", "license": "customer terms", "consent_basis": "contract", "owner": "data", "retention_window": "90d", "redaction_coverage": "pii"}]}
    )

    assert plan["blockers"] == []
    assert plan["lineage_checks"][0]["name"] == "support transcripts"
    assert set(plan) >= {"lineage_checks", "provenance_checks", "license_checks", "consent_basis_checks", "retention_window_checks", "redaction_coverage_checks", "approver_signoff"}


def test_training_data_lineage_review_plan_blocks_missing_required_fields_and_preserves_metadata() -> None:
    source = {"datasets": [{"dataset": "web crawl", "source": "crawl", "owner": "data", "evidence_id": "ev-7", "metadata": {"region": "us"}}]}
    plan = generate_training_data_lineage_review_plan(source)

    assert [row["missing_field"] for row in plan["blockers"]] == ["license", "consent_basis"]
    assert generate_training_data_lineage_review_plan(source) == plan
    assert plan["lineage_checks"][0]["evidence_id"] == "ev-7"
    assert plan["lineage_checks"][0]["metadata"] == {"region": "us"}

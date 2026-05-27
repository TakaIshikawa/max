from __future__ import annotations

from max.spec.inference_data_residency_review_plan import generate_inference_data_residency_review_plan


def test_inference_data_residency_review_plan_normalizes_regions_and_flags_risk() -> None:
    plan = generate_inference_data_residency_review_plan({"metadata": {"inference_data_residency_review": {"regions": [{"region": "us-east-1", "data_category": "prompts", "residency": "in_region"}, {"region": "eu-west-1", "data_category": "logs", "residency": "cross_border"}], "transfer_checks": ["routing policy check"], "provider_controls": ["region pinning"], "log_storage_residency": ["bucket region audit"], "exception_approvals": ["legal exception"], "audit_evidence": ["provider export"]}}})

    assert set(plan) >= {"region_inventory", "transfer_checks", "provider_controls", "log_storage_residency", "exception_approvals", "audit_evidence", "evidence_references"}
    assert [row["region"] for row in plan["region_inventory"]] == ["eu-west-1", "us-east-1"]
    assert plan["review_findings"][0]["review_severity"] == "high"


def test_inference_data_residency_review_plan_unknown_defaults_to_medium() -> None:
    plan = generate_inference_data_residency_review_plan({})

    assert plan["region_inventory"][0]["review_severity"] == "medium"
    assert plan["summary"]["review_finding_count"] == 1

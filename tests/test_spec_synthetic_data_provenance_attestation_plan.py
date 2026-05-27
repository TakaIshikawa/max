from __future__ import annotations

from max.spec.synthetic_data_provenance_attestation_plan import (
    generate_synthetic_data_provenance_attestation_plan,
)


def test_synthetic_data_provenance_attestation_plan_sorts_dataset_aliases() -> None:
    plan = generate_synthetic_data_provenance_attestation_plan({"metadata": {"synthetic_data_provenance_attestation": {"datasets": [{"name": "zeta", "source": "support corpus", "generator": "gpt", "privacy_attestation": "passed"}, {"dataset_id": "alpha", "source": "billing fixtures", "generator": "rules", "privacy_attestation": "passed"}], "generation_methods": ["LLM generation"], "source_constraints": ["licensed sources"], "privacy_attestations": ["memorization test"], "permitted_uses": ["eval only"], "retention_controls": ["30 days"], "approval_evidence": ["privacy approval"]}}})

    assert set(plan) >= {"dataset_inventory", "generation_methods", "source_constraints", "privacy_attestations", "permitted_uses", "retention_controls", "approval_evidence", "evidence_references"}
    assert [row["dataset_id"] for row in plan["dataset_inventory"]] == ["alpha", "zeta"]
    assert plan["review_findings"] == []


def test_synthetic_data_provenance_attestation_plan_flags_missing_provenance_and_privacy() -> None:
    plan = generate_synthetic_data_provenance_attestation_plan({})

    assert {finding["severity"] for finding in plan["review_findings"]} == {"high", "medium"}

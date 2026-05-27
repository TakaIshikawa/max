from __future__ import annotations

from max.spec.third_party_subprocessor_review_plan import generate_third_party_subprocessor_review_plan


def test_third_party_subprocessor_review_plan_flags_missing_dpa() -> None:
    plan = generate_third_party_subprocessor_review_plan({"metadata": {"third_party_subprocessor_review": {"processors": [{"processor": "Vendor", "dpa_status": "missing", "security_attestation": "current"}]}}})

    assert plan["risk_findings"][0]["required_step"] == "collect executed DPA"


def test_third_party_subprocessor_review_plan_flags_cross_border_processing() -> None:
    plan = generate_third_party_subprocessor_review_plan({"metadata": {"third_party_subprocessor_review": {"processors": [{"processor": "Vendor", "residency": "cross-border", "dpa_status": "current", "security_attestation": "current"}]}}})

    assert plan["risk_findings"][0]["required_step"] == "complete transfer impact assessment"


def test_third_party_subprocessor_review_plan_flags_stale_attestation() -> None:
    plan = generate_third_party_subprocessor_review_plan({"metadata": {"third_party_subprocessor_review": {"processors": [{"processor": "Vendor", "dpa_status": "current", "security_attestation": "stale"}]}}})

    assert plan["risk_findings"][0]["required_step"] == "collect SOC 2 or equivalent attestation"


def test_third_party_subprocessor_review_plan_uses_deterministic_alias_default() -> None:
    first = generate_third_party_subprocessor_review_plan({"metadata": {"third_party_subprocessor_review": {"processors": [{"processor": "Vendor"}]}}})
    second = generate_third_party_subprocessor_review_plan({"metadata": {"third_party_subprocessor_review": {"processors": [{"processor": "Vendor"}]}}})

    assert first == second
    assert first["processor_inventory"][0]["alias"] == "Vendor"

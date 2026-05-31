from __future__ import annotations

from max.spec.data_processor_exit_plan import generate_data_processor_exit_plan


def test_data_processor_exit_sorts_customer_data_first_and_sections() -> None:
    plan = generate_data_processor_exit_plan({"metadata": {"data_processor_exit": {"processors": [{"processor": "logs", "data_class": "telemetry"}, {"processor": "crm", "data_class": "customer pii", "replacement_owner": "ops", "deletion_attestation": "yes"}]}}})
    assert plan["processor_inventory"][0]["name"] == "crm"
    assert plan["exit_trigger"] and plan["data_transfer"] and plan["access_revocation"] and plan["stakeholder_signoff"]


def test_data_processor_exit_flags_missing_attestation_and_owner() -> None:
    plan = generate_data_processor_exit_plan({"metadata": {"data_processor_exit": {"processor_inventory": [{"vendor": "vendor-a", "data_class": "customer data"}]}}})
    assert "Assign replacement owner" in plan["replacement_readiness"][0]["description"]
    assert "Obtain deletion attestation" in plan["deletion_attestation"][0]["description"]


def test_data_processor_exit_defaults_inventory() -> None:
    plan = generate_data_processor_exit_plan({})
    assert plan["processor_inventory"]

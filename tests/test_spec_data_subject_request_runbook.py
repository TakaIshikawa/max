from __future__ import annotations

from max.spec.data_subject_request_runbook import (
    KIND,
    SCHEMA_VERSION,
    generate_data_subject_request_runbook,
)


def test_data_subject_request_runbook_access_export_request() -> None:
    runbook = generate_data_subject_request_runbook(
        {"request_type": "export", "systems": ["app db", "zendesk"]}
    )

    assert runbook["schema_version"] == SCHEMA_VERSION
    assert runbook["kind"] == KIND
    assert runbook["request_classification"]["primary_type"] == "export"
    assert runbook["system_lookup"] == ["app db", "zendesk"]
    assert "Generate export package and validate redaction boundaries." in runbook["fulfillment_steps"]
    assert runbook["deletion_export_handling"]["export_format"] == "machine-readable JSON and CSV where available"
    assert runbook["sla_tracking"]["fulfillment"] == "30 calendar days"
    assert "final response artifact and timestamped delivery record" in runbook["audit_evidence"]


def test_data_subject_request_runbook_deletion_request_strengthens_exceptions_and_evidence() -> None:
    runbook = generate_data_subject_request_runbook(
        {"request_type": "deletion", "sla": "21 calendar days", "legal_owner": "Privacy Counsel"}
    )

    assert runbook["request_type"] == "deletion"
    assert runbook["sla_tracking"]["fulfillment"] == "21 calendar days"
    assert runbook["deletion_export_handling"]["deletion_mode"] == (
        "hard delete or anonymize after retention review"
    )
    assert any("retention review" in step for step in runbook["fulfillment_steps"])
    assert any("tax, financial" in item for item in runbook["exceptions"])
    assert any("deletion job IDs" in item for item in runbook["audit_evidence"])
    assert runbook["escalation"][1]["owner"] == "Privacy Counsel"

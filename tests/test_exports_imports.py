from __future__ import annotations


def test_new_export_reports_are_importable_from_package() -> None:
    from max.exports import (
        build_source_adapter_error_budget_report_export,
        build_source_credential_expiry_report,
        generate_source_credential_expiry_report,
        generate_source_fetch_allocation_drift_report,
    )

    assert callable(build_source_adapter_error_budget_report_export)
    assert callable(build_source_credential_expiry_report)
    assert callable(generate_source_credential_expiry_report)
    assert callable(generate_source_fetch_allocation_drift_report)

from __future__ import annotations

from max.exports import (
    build_source_adapter_error_budget_report_export,
    build_source_credential_expiry_report,
    render_source_adapter_error_budget_report_json,
    render_source_adapter_error_budget_report_markdown,
    render_source_credential_expiry_report_json,
    render_source_credential_expiry_report_markdown,
)


def test_new_export_report_symbols_are_importable() -> None:
    assert callable(build_source_adapter_error_budget_report_export)
    assert callable(render_source_adapter_error_budget_report_json)
    assert callable(render_source_adapter_error_budget_report_markdown)
    assert callable(build_source_credential_expiry_report)
    assert callable(render_source_credential_expiry_report_json)
    assert callable(render_source_credential_expiry_report_markdown)

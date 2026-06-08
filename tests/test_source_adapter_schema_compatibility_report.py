from __future__ import annotations

from max.exports import generate_source_adapter_schema_compatibility_report as exported
from max.exports.source_adapter_schema_compatibility_report import generate_source_adapter_schema_compatibility_report


def test_source_adapter_schema_compatibility_report_flags_missing_and_deprecated_fields() -> None:
    report = generate_source_adapter_schema_compatibility_report(
        [
            {"adapter": "github", "source": "issues", "required_fields": ["id", "title"], "provided_fields": ["id"]},
            {"adapter": "slack", "source": "messages", "required_fields": ["id"], "provided_fields": ["id", "legacy"], "deprecated_fields": ["legacy"]},
            {"adapter": "zendesk", "source": "tickets", "required_fields": ["id"], "provided_fields": ["id"]},
        ]
    )

    assert exported is generate_source_adapter_schema_compatibility_report
    assert [row["status"] for row in report["rows"]] == ["incompatible", "warning", "compatible"]
    assert report["rows"][0]["missing_fields"] == ["title"]
    assert report["summary"]["incompatible_count"] == 1
